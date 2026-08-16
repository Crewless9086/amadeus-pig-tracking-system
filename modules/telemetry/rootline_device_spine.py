"""Provider-neutral commissioning contracts; descriptive, never authority granting."""
from __future__ import annotations
from dataclasses import dataclass
from enum import Enum
from typing import Mapping, Protocol

CONTRACT_VERSION = "rootline_device_spine.v1"

class CommissioningStage(str, Enum):
    REGISTERED = "registered"
    PROVIDER_DISCOVERED = "provider_discovered"
    READBACK_PROVEN = "readback_proven"
    BOUNDED_ACTUATION_READY = "bounded_actuation_ready"
    PHYSICAL_IDENTITY_PROVEN = "physical_identity_proven"
    FAIL_STOP_PROVEN = "fail_stop_proven"
    REPLAY_PROVEN = "replay_proven"
    DEPENDENCIES_PROVEN = "operational_dependencies_proven"
    SUPERVISED = "supervised"
    STANDING_ACTIVE = "standing_active"

STAGE_ORDER = tuple(stage.value for stage in CommissioningStage)
DEVICE_PROFILES = {
    "gravity_irrigation_valve": {"requires_flow": False, "safe_state": "OFF"},
    "independent_mixer_valve": {"requires_flow": False, "safe_state": "OFF"},
    "flow_dependent_injection_valve": {"requires_flow": True, "safe_state": "OFF"},
    "pump": {"requires_flow": False, "safe_state": "OFF", "strict": True},
    "breaker": {"requires_flow": False, "safe_state": "OFF", "strict": True},
    "sensor": {"read_only": True, "safe_state": "UNCHANGED"},
    "generic_relay_output": {"requires_flow": False, "safe_state": "OFF"},
}

class Actuator(Protocol):
    def read_state(self, device: Mapping) -> Mapping: ...
    def set_on(self, device: Mapping, execution: Mapping) -> Mapping: ...
    def set_off(self, device: Mapping, execution: Mapping) -> Mapping: ...
    def arm_auto_off(self, device: Mapping, seconds: int, execution: Mapping) -> Mapping: ...
    def verify_on(self, device: Mapping, execution: Mapping) -> Mapping: ...
    def verify_off(self, device: Mapping, execution: Mapping) -> Mapping: ...
    def repeat_safe_off(self, device: Mapping, execution: Mapping) -> Mapping: ...

def validate_device(record: Mapping) -> bool:
    required = ("provider", "provider_account_binding", "device_id", "channel",
        "physical_name", "device_type", "adapter_profile", "safe_state",
        "maximum_runtime_seconds", "native_fail_stop_seconds", "readback",
        "physical_effect", "dependencies", "manual_isolation",
        "commissioning_stage", "standing_authority")
    if any(key not in record for key in required):
        raise ValueError("rootline_device_spine_field_missing")
    if record["device_type"] not in DEVICE_PROFILES:
        raise ValueError("rootline_device_profile_unsupported")
    if record["commissioning_stage"] not in STAGE_ORDER:
        raise ValueError("rootline_commissioning_stage_invalid")
    if record["standing_authority"] is True and record["commissioning_stage"] != "standing_active":
        raise ValueError("rootline_standing_authority_unproven")
    if DEVICE_PROFILES[record["device_type"]].get("strict") and record["standing_authority"]:
        if record.get("physical_identity_proven") is not True or record.get("fail_stop_proven") is not True:
            raise ValueError("rootline_strict_device_proof_missing")
    return True

def manager_stage_projection(record: Mapping) -> dict:
    """Project asserted evidence for review; never returns action authority."""
    validate_device(record)
    stage = record["commissioning_stage"]
    index = STAGE_ORDER.index(stage) + 1
    asserted_working = stage == "standing_active" and record["standing_authority"] is True
    blocker = "" if asserted_working else str(record.get("exact_blocker") or "Unknown")
    return {"contract_version": CONTRACT_VERSION, "exact_device": record["physical_name"],
        "stage_number": index, "stage_state": stage, "working_now": "Unknown",
        "asserted_working_state": asserted_working, "execution_authority": False,
        "exact_blocker": blocker, "next_safe_action": "none" if asserted_working else
            str(record.get("next_safe_action") or "review_required"),
        "physical_proof_invented": False}
