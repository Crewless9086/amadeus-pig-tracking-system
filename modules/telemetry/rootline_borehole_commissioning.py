"""Command-inert commissioning assessment for the reported Borehole 1 MINI R4."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import json

from modules.telemetry.rootline_device_registry import get_device_contract

VERSION="rootline_borehole_commissioning_readiness.v1"


def assess_borehole_commissioning_readiness(readback, *, now=None):
    now=_aware(now or datetime.now(timezone.utc)); device=get_device_contract("BOREHOLE-1-MINI-R4-CH1")
    readback=dict(readback or {}); observed=_time(readback.get("retrieved_at") or readback.get("trusted_receipt_at"))
    channels=list(readback.get("channels") or ())
    exact=(readback.get("device_id")==device["device_id"]
        and readback.get("device_name")==device["device_name"]
        and str(readback.get("model") or "").upper().replace(" ","")=="MINIR4")
    current=(observed is not None and not now<observed and now-observed<=timedelta(minutes=5))
    all_off=bool(channels) and all(row.get("output_state")=="OFF" for row in channels)
    fail_off=(readback.get("native_auto_off_enabled") is True
        and type(readback.get("native_auto_off_seconds")) is int
        and 1<=readback["native_auto_off_seconds"]<=300)
    conflicts=(readback.get("timers_enabled") is False
        and readback.get("scenes_enabled") is False
        and readback.get("interlock_enabled") is False
        and readback.get("power_restoration_state")=="OFF")
    blockers=[]
    if not exact: blockers.append("exact_provider_identity_unproven")
    if readback.get("online") is not True or not current: blockers.append("fresh_online_readback_unproven")
    if not all_off: blockers.append("all_outputs_off_unproven")
    if not fail_off: blockers.append("native_fail_off_not_configured_or_verified")
    if not conflicts: blockers.append("conflicting_paths_not_proven_disabled")
    material={"contract_version":VERSION,"identity":device["identity"],
        "device_id":device["device_id"],"channel":1,"maximum_test_seconds":30,
        "native_fail_off_required":True,"all_other_channels_off_required":True,
        "no_on_retry":True,"provider_off_verification_required":True,
        "physical_observations_required":["pump_started","water_flow_observed",
            "pump_stopped","water_flow_stopped"],"blockers":blockers,
        "commissioned":False,"authority_flag_enabled":False}
    digest=_digest(material)
    return {**material,"readiness_sha256":digest,
        "status":"ready_for_protected_preview" if not blockers else "Hold",
        "eligible_for_card":not blockers,"hardware_commands":0,"provider_control_calls":0,
        "writes_farm_data":False}


def _digest(value): return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(",",":"),default=str).encode()).hexdigest()
def _aware(value):
    if not isinstance(value,datetime) or value.tzinfo is None: raise ValueError("aware_time_required")
    return value.astimezone(timezone.utc)
def _time(value):
    try:
        parsed=datetime.fromisoformat(str(value or "").replace("Z","+00:00"))
        return parsed.astimezone(timezone.utc) if parsed.tzinfo else None
    except (TypeError,ValueError): return None
