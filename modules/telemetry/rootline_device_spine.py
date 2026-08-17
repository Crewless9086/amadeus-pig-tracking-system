"""Provider-neutral commissioning contracts; descriptive, never authority granting."""
from __future__ import annotations
from dataclasses import dataclass
from enum import Enum
import hashlib
import json
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

def store_device_record(record: Mapping, *, connect_factory) -> dict:
    """Persist validated commissioning truth; this does not grant execution authority."""
    validate_device(record)
    material = json.dumps(dict(record), sort_keys=True, separators=(",", ":"), default=str)
    digest = hashlib.sha256(material.encode()).hexdigest()
    authority = record.get("authority_envelope") if isinstance(
        record.get("authority_envelope"), Mapping) else {}
    key = f"{record['provider']}:{record['provider_account_binding']}:{record['device_id']}:{record['channel']}"
    with connect_factory() as db, db.cursor() as cur:
        cur.execute("""insert into app_private.rootline_device_registry(
          device_key,contract_version,device_record,commissioning_stage,
          standing_authority_id,standing_authority_version,authority_revoked,evidence_digest)
          values(%s,%s,%s::jsonb,%s,%s,%s,%s,%s)
          on conflict(device_key) do update set contract_version=excluded.contract_version,
          device_record=excluded.device_record,commissioning_stage=excluded.commissioning_stage,
          standing_authority_id=excluded.standing_authority_id,
          standing_authority_version=excluded.standing_authority_version,
          authority_revoked=excluded.authority_revoked,evidence_digest=excluded.evidence_digest,
          updated_at=now()""", (key, CONTRACT_VERSION, material,
          record["commissioning_stage"], authority.get("standing_authority_id"),
          authority.get("version"), bool(authority.get("revoked")), digest))
    return {"success": True, "device_key": key, "evidence_digest": digest,
        "execution_authority": False}

def load_device_record(device_key: str, *, connect_factory) -> dict | None:
    with connect_factory() as db, db.cursor() as cur:
        cur.execute("""select contract_version,device_record,evidence_digest
          from app_private.rootline_device_registry where device_key=%s""", (str(device_key),))
        row = cur.fetchone()
    if not row:
        return None
    record = row[1] if isinstance(row[1], Mapping) else {}
    validate_device(record)
    material = json.dumps(dict(record), sort_keys=True, separators=(",", ":"), default=str)
    if row[0] != CONTRACT_VERSION or hashlib.sha256(material.encode()).hexdigest() != row[2]:
        raise ValueError("rootline_device_registry_digest_mismatch")
    return {"device_key": str(device_key), "device_record": dict(record),
        "evidence_digest": str(row[2]), "execution_authority": False}

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
    profile = DEVICE_PROFILES[record["device_type"]]
    if str(record["safe_state"]) != str(profile["safe_state"]):
        raise ValueError("rootline_device_safe_state_mismatch")
    if not isinstance(record["channel"], int) or record["channel"] < 0:
        raise ValueError("rootline_device_channel_invalid")
    for field in ("maximum_runtime_seconds", "native_fail_stop_seconds"):
        if not isinstance(record[field], int) or record[field] < 0:
            raise ValueError("rootline_device_runtime_bound_invalid")
    if not profile.get("read_only") and (
            record["maximum_runtime_seconds"] <= 0
            or record["native_fail_stop_seconds"] <= 0
            or record["native_fail_stop_seconds"] > record["maximum_runtime_seconds"]):
        raise ValueError("rootline_device_fail_stop_bound_invalid")
    if record["standing_authority"] is True and record["commissioning_stage"] != "standing_active":
        raise ValueError("rootline_standing_authority_unproven")
    if record["standing_authority"] is True:
        evidence = record.get("commissioning_evidence")
        required = ("provider_discovered", "readback_proven", "bounded_actuation_ready",
            "physical_identity_proven", "fail_stop_proven", "replay_proven",
            "operational_dependencies_proven", "supervised")
        if (not isinstance(evidence, Mapping)
                or any(not str(evidence.get(key) or "").strip() for key in required)):
            raise ValueError("rootline_standing_authority_evidence_missing")
        authority = record.get("authority_envelope")
        if (not isinstance(authority, Mapping)
                or not str(authority.get("standing_authority_id") or "").strip()
                or not str(authority.get("version") or "").strip()
                or authority.get("revoked") is not False):
            raise ValueError("rootline_standing_authority_envelope_invalid")
        if profile.get("strict") and (
                record.get("independent_physical_identity_proven") is not True
                or record.get("independent_fail_stop_proven") is not True):
            raise ValueError("rootline_strict_device_proof_missing")
    return True

def manager_stage_projection(record: Mapping) -> dict:
    """Project asserted evidence for review; never returns action authority."""
    validate_device(record)
    stage = record["commissioning_stage"]
    index = STAGE_ORDER.index(stage) + 1
    evidence_bound = stage == "standing_active" and record["standing_authority"] is True
    blocker = "" if evidence_bound else str(record.get("exact_blocker") or "Unknown")
    return {"contract_version": CONTRACT_VERSION, "exact_device": record["physical_name"],
        "stage_number": index, "stage_state": stage, "working_now": "Unknown",
        "asserted_working_state": False, "standing_authority_evidence_bound": evidence_bound,
        "execution_authority": False,
        "exact_blocker": blocker, "next_safe_action": "none" if evidence_bound else
            str(record.get("next_safe_action") or "review_required"),
        "physical_proof_invented": False}
