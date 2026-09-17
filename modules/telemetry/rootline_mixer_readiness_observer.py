"""Zero-control-call readiness observation for the registered fertilizer mixer.

This collector is deliberately a reader.  It reuses the governed eWeLink token
store/readback adapter and the canonical ROOTLINE execution ledger, and returns
only the bounded candidate facts consumed by Oom Sakkie's existing manager
case rail.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import json

from modules.telemetry.rootline_device_registry import get_device_contract


DEVICE_ID = "100204d497"
DEVICE_IDENTITY = "FERTILIZER-MIXER-CH2"
CHANNEL = 2
NATIVE_FAIL_STOP_SECONDS = 300
CONTRACT_VERSION = "rootline_mixer_readiness_observer.v1"


def collect_mixer_readiness(*, now: datetime, token_store=None, readback=None,
                            execution_store=None, environ=None):
    """Return one stable ROOTLINE manager candidate from current provider truth."""
    from modules.telemetry.rootline_ewelink_oauth_store import PostgresOAuthTokenStore
    from modules.telemetry.rootline_ewelink_readback import read_registered_device
    from modules.telemetry.rootline_irrigation_execution_store import (
        rootline_irrigation_execution_store,
    )

    observed_at = _aware(now)
    contract = get_device_contract(DEVICE_IDENTITY)
    if not _contract_is_exact(contract):
        raise ValueError("rootline_mixer_registry_binding_invalid")
    reader = readback or read_registered_device
    provider = reader(
        DEVICE_ID,
        token_store=token_store or PostgresOAuthTokenStore(),
        environ=environ,
        now=observed_at,
    )
    ledger = execution_store or rootline_irrigation_execution_store
    active = ledger("load_active_auxiliary", None)
    channel = _channel(provider)
    checks = {
        "provider_account_bound": provider.get("authoritative") is True,
        "provider_observation_fresh": provider.get("observation_fresh") is True,
        "provider_timestamp_not_stale": provider.get("provider_timestamp_fresh") is not False,
        "device_bound": provider.get("device_id") == DEVICE_ID,
        "channel_bound": channel.get("channel") == CHANNEL,
        "current_off": channel.get("output_state") == "OFF",
        "native_fail_stop_enabled": channel.get("native_auto_off_enabled") is True,
        "native_fail_stop_seconds": channel.get("native_auto_off_seconds") == NATIVE_FAIL_STOP_SECONDS,
        "no_conflicting_active_execution": active is None,
        "zero_control_calls": provider.get("provider_control_calls") == 0,
    }
    ready = all(checks.values())
    reason = "ready" if ready else "hold"
    material = {
        "contract_version": CONTRACT_VERSION,
        "registry_contract_sha256": contract["contract_sha256"],
        "device_id": DEVICE_ID,
        "channel": CHANNEL,
        "checks": checks,
        "conflicting_execution_id": str((active or {}).get("execution_id") or ""),
        "readiness": reason,
    }
    digest = hashlib.sha256(json.dumps(material, sort_keys=True,
        separators=(",", ":")).encode()).hexdigest()
    failed = sorted(key for key, value in checks.items() if not value)
    next_at = observed_at + timedelta(minutes=5)
    return [{
        "dedupe_key": "rootline-readiness:fertilizer-mixer-ch2",
        "specialist": "ROOTLINE",
        "urgency": "watch" if ready else "urgent",
        "task_class": "informational_watch" if ready else "status_reconciliation",
        # Healthy controller readiness is useful equipment-health evidence, not
        # owner work.  Failed or stale readiness remains one shared exception
        # owned by ROOTLINE's existing reassessment cycle.
        "attention_visibility": ("equipment_health_only" if ready
                                 else "owner_attention_exception"),
        "presentation_identity": {
            "human_name": "Fertilizer mixer",
            "stable_reference": DEVICE_IDENTITY,
        },
        "equipment_identity": DEVICE_IDENTITY,
        "equipment_lifecycle": "ready_for_commissioning" if ready else "held",
        "equipment_evidence": {
            "provider_readiness_proven": ready,
            "current_state_off": checks["current_off"],
        },
        "evidence_refs": [
            f"readiness:{digest}",
            f"registry:{contract['contract_sha256']}",
            f"observed:{str(provider.get('retrieved_at') or observed_at.isoformat())}",
        ],
        "unknowns": failed,
        "summary": ("Fertilizer mixer controller is ready for future commissioning. Automatic mixing is not proven enabled."
                    if ready else
                    "Fertilizer mixer controller readiness requires ROOTLINE review."),
        "next_action": ("No owner action now; ROOTLINE will reassess on the next existing manager cycle."
                        if ready else
                        "Keep automatic mixing disabled; ROOTLINE will reassess the failed readiness checks on the next existing manager cycle."),
        "next_reassessment_at": next_at.isoformat(),
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
