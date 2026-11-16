"""Timestamped canonical mixer observations for the existing manager case rail.

No provider poll or command is performed. Runtime safety readers retain their
own fresh evidence requirements; a historical output is never current readiness.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import json

from modules.telemetry.rootline_device_registry import get_device_contract


DEVICE_ID = "100204d497"
DEVICE_IDENTITY = "FERTILIZER-MIXER-CH2"
CHANNEL = 2
# Exact commissioned CH2 envelope; readiness never grants actuation authority.
NATIVE_FAIL_STOP_SECONDS = 1800
CONTRACT_VERSION = "rootline_mixer_readiness_observer.v2"


def collect_mixer_readiness(*, now: datetime, token_store=None, readback=None,
                            execution_store=None, environ=None, _observation_purpose="mixer_readiness"):
    """Project timestamped canonical execution evidence without provider polls.

    This informational projection never establishes command readiness. Active
    operation continues to use the runtime's fresh safety and output readers.
    """
    from modules.telemetry.rootline_irrigation_execution_store import rootline_irrigation_execution_store
    observed_at = _aware(now)
    contract = get_device_contract(DEVICE_IDENTITY)
    if not _contract_is_exact(contract):
        raise ValueError("rootline_mixer_registry_binding_invalid")
    ledger = execution_store or rootline_irrigation_execution_store
    active = ledger("load_active_auxiliary", DEVICE_IDENTITY)
    history = ledger("load_auxiliary_history", DEVICE_IDENTITY) or []
    observations = []
    for execution in [*history, active]:
        if (not isinstance(execution, dict)
                or execution.get("auxiliary_device_id") != DEVICE_IDENTITY
                or execution.get("device_id") != DEVICE_ID
                or execution.get("channel") != CHANNEL):
            continue
        for name in ("start_evidence", "shutdown_evidence"):
            proof = execution.get(name) or {}
            if (not isinstance(proof, dict) or proof.get("authoritative") is not True
                    or proof.get("device_id") != DEVICE_ID or proof.get("channel") != CHANNEL
                    or proof.get("state") not in {"ON", "OFF"} or not proof.get("evidence_id")):
                continue
            try:
                timestamp = datetime.fromisoformat(str(proof.get("retrieved_at")).replace("Z", "+00:00"))
                if timestamp.tzinfo is None or timestamp > observed_at:
                    continue
            except (ValueError, TypeError):
                continue
            observations.append((timestamp, proof))
    timestamp, proof = max(observations, key=lambda row: row[0]) if observations else (None, {})
    fresh = timestamp is not None and observed_at-timestamp <= timedelta(seconds=120)
    current = proof.get("state") if fresh else "Unknown"
    material = {"contract_version": CONTRACT_VERSION, "registry": contract["contract_sha256"], "evidence_id": proof.get("evidence_id"),
        "observed_at": timestamp.isoformat() if timestamp else None,
        "current_state": current, "active_execution_id": (active or {}).get("execution_id")}
    digest = hashlib.sha256(json.dumps(material, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    refs = [f"readiness:{digest}", f"registry:{contract['contract_sha256']}", "projection:rootline_canonical_output.v1"]
    if timestamp is not None:
        refs.extend([f"canonical:{proof['evidence_id']}", f"observed:{timestamp.isoformat()}"])
    return [{
        "dedupe_key": "rootline-readiness:fertilizer-mixer-ch2", "specialist": "ROOTLINE",
        "urgency": "watch", "task_class": "informational_watch",
        "attention_visibility": "equipment_health_only",
        "presentation_identity": {"human_name": "Fertilizer mixer", "stable_reference": DEVICE_IDENTITY},
        "equipment_identity": DEVICE_IDENTITY, "equipment_lifecycle": "registered",
        "equipment_evidence": {"provider_readiness_proven": False, "current_state_off": fresh and current == "OFF",
            "canonical_observation_only": True},
        "canonical_observation": {"current_state": current,
            "last_observed_state": proof.get("state", "Unknown"),
            "observed_at": timestamp.isoformat() if timestamp else None,
            "observation_fresh": fresh, "source": "canonical_execution"},
        "evidence_refs": refs, "unknowns": ["current_command_readiness"] + ([] if fresh else ["current_output_state"]),
        "summary": ("Fertilizer mixer last recorded " + proof["state"] + " at " + timestamp.isoformat() +
            (". Current command readiness requires the runtime safety check." if fresh else ". Current state is Unknown."))
            if timestamp else "Fertilizer mixer has no qualified canonical output observation. Current state is Unknown.",
        "next_action": "ROOTLINE continues its existing operating and safety checks; this status grants no command permission.",
        "next_reassessment_at": (observed_at+timedelta(minutes=5)).isoformat(),
    }]


def _contract_is_exact(contract):
    return bool(contract
        and contract.get("device_id") == DEVICE_ID
        and contract.get("channel") == CHANNEL
        and contract.get("provider_account_binding") == "ewelink_owner_account"
        and contract.get("native_fail_stop_seconds") == NATIVE_FAIL_STOP_SECONDS
        and contract.get("authority_flag") == "ROOTLINE_FERTILIZER_MIXING_ENABLED")


def _channel(provider):
    channels = provider.get("channels") if isinstance(provider, dict) else None
    matches = [row for row in channels or () if row.get("channel") == CHANNEL]
    if len(matches) != 1:
        return {}
    return matches[0]


def _aware(value):
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)
