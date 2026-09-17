"""Executive closure for delivered code whose business outcome is unfinished."""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any, Mapping

from modules.charlie.final_readiness import evaluate_final_readiness


TERMINAL_DELIVERY_STATUSES = {"merged", "deployed", "done"}


def operational_outcome_closure(mission: Mapping[str, Any]) -> dict[str, Any]:
    """Describe unfinished business without changing protected state."""
    mission = dict(mission) if isinstance(mission, Mapping) else {}
    mission_id = str(mission.get("mission_id") or "").strip()
    status = str(mission.get("status") or "").strip().lower()
    metadata = mission.get("metadata") if isinstance(mission.get("metadata"), Mapping) else {}
    packet = metadata.get("review_packet") if isinstance(metadata.get("review_packet"), Mapping) else {}
    tracked_delivery = bool(packet.get("changed_files") or packet.get("protected_operations") or metadata.get("protected_operations"))
    readiness = evaluate_final_readiness(mission)
    pending = list(readiness.get("pending_gate_keys") or [])
    unfinished = tracked_delivery and status in TERMINAL_DELIVERY_STATUSES and not readiness.get("final_operational_ready")
    fingerprint = _fingerprint({"mission_id": mission_id, "status": status, "pending": pending})
    follow_up_id = f"CHARLIE-OUTCOME-{fingerprint[:16].upper()}" if unfinished else ""
    owner_required = "migration_approval" in pending
    next_action = str(readiness.get("next_action") or "Verify the delivered business outcome.")
    return {
        "version": "charlie-operational-outcome-v1",
        "mission_id": mission_id,
        "delivery_status": status,
        "tracked_delivery": tracked_delivery,
        "business_capability_status": "not_operational" if unfinished else "operational",
        "unfinished": unfinished,
        "owner_required": owner_required,
        "pending_gate_keys": pending,
        "next_action": next_action,
        "business_impact": (
            "Code delivery is complete, but the requested capability is not yet verified as active in production."
            if unfinished else "The delivered capability has all required operational evidence."
        ),
        "follow_up_mission_id": follow_up_id,
        "fingerprint": fingerprint,
        "observed_at": datetime.now(timezone.utc).isoformat(),
    }


def outcome_follow_up_mission(mission: Mapping[str, Any], closure: Mapping[str, Any]) -> dict[str, Any]:
    mission = dict(mission) if isinstance(mission, Mapping) else {}
    closure = dict(closure) if isinstance(closure, Mapping) else {}
    mission_id = str(mission.get("mission_id") or "")
    follow_up_id = str(closure.get("follow_up_mission_id") or "")
    pending = list(closure.get("pending_gate_keys") or [])
    migration = any(key.startswith("migration_") for key in pending)
    protected = ([{"operation": "apply_migration", "status": "owner_gated"}] if migration else [])
    return {
        "mission_id": follow_up_id,
        "status": "new",
        "title": f"Activate operational outcome: {mission.get('title') or mission_id}",
        "raw_text": (
            f"Close the unfinished operational outcome for {mission_id}.\n"
            f"Pending gates: {', '.join(pending)}.\n"
            f"Required next action: {closure.get('next_action')}.\n"
            "Prepare current evidence and request only the exact protected authority that remains."
        ),
        "urgency": mission.get("urgency") or "P1",
        "mission_type": "operational outcome closure",
        "approval_level": "LEVEL 5" if migration else "LEVEL 4",
        "metadata": {
            "mission_family": {"parent_mission_id": mission_id, "relationship": "operational_outcome_follow_up"},
            "outcome_closure": dict(closure),
            "protected_operations": protected,
            "queue": {"business_value": 15, "revenue_impact": 5},
        },
    }


def _fingerprint(value: object) -> str:
    import json

    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:24]
