"""Deterministic boundaries for CHARLIE delegated reviews and queue selection."""

from __future__ import annotations

import re

from modules.charlie.final_readiness import evaluate_final_readiness
from modules.charlie.pr_reconciliation import mission_pr_reference, reconciliation_decision


PROTECTED_TERMS = {
    "customer send", "send to customer", "public post", "publish publicly",
    "payment", "deposit", "refund", "reservation", "reserve stock",
    "lifecycle write", "purpose write", "production delete", "destructive",
    "credential", "secret", "authentication", "authorization", "owner access",
    "schema migration", "database migration", "production data cleanup",
}
PROTECTED_PATH_MARKERS = (
    "supabase/migrations/", ".github/", ".env", "auth", "owner_access",
    "payment", "deposit", "reservation", "lifecycle", "purpose_assignment",
)


def delegated_review_assessment(mission, *, pr_state=None, dependency_states=None):
    mission = mission if isinstance(mission, dict) else {}
    if mission.get("status") != "pr_ready":
        return _decision(False, "mission_not_pr_ready")
    flags = mission_risk_flags(mission)
    if flags:
        return _decision(False, "protected_surface_requires_owner", risk_flags=flags)
    readiness = evaluate_final_readiness(mission)
    if not readiness.get("can_authorize_release"):
        return _decision(False, "deterministic_readiness_incomplete", readiness=readiness)
    reference = mission_pr_reference(mission)
    if not reference:
        return _decision(False, "authoritative_pr_required", readiness=readiness)
    if pr_state is None:
        return _decision(True, "authoritative_pr_check_required", action="verify_and_delegate_review", pr_reference=reference, readiness=readiness)
    reconciliation = reconciliation_decision(
        mission, pr_state, dependency_states=dependency_states,
    )
    if reconciliation.get("action") not in {"mark_pr_ready", "none"} or (
        reconciliation.get("action") == "none" and reconciliation.get("reason") != "pr_ready_is_sticky"
    ):
        return _decision(False, "authoritative_pr_not_green", reconciliation=reconciliation, readiness=readiness)
    return _decision(True, "delegated_review_ready", action="delegate_final_review", pr_reference=reference, reconciliation=reconciliation, readiness=readiness)


def queue_candidate_assessment(mission):
    mission = mission if isinstance(mission, dict) else {}
    if mission.get("status") != "new":
        return _decision(False, "mission_not_new")
    flags = mission_risk_flags(mission)
    if flags:
        return _decision(False, "protected_surface_requires_owner", risk_flags=flags)
    approval = str(mission.get("approval_level") or "LEVEL 3").upper()
    match = re.search(r"(\d+)", approval)
    if match and int(match.group(1)) > 3:
        return _decision(False, "approval_level_requires_owner")
    return _decision(True, "safe_queue_candidate", action="approve_next_work")


def mission_risk_flags(mission):
    metadata = mission.get("metadata") if isinstance(mission.get("metadata"), dict) else {}
    packet = metadata.get("review_packet") if isinstance(metadata.get("review_packet"), dict) else {}
    changed = packet.get("changed_files") if isinstance(packet.get("changed_files"), list) else []
    paths = [str(path).replace("\\", "/").lower() for path in changed]
    flags = [f"protected_path:{path}" for path in paths if any(marker in path for marker in PROTECTED_PATH_MARKERS)]
    text = " ".join(str(value or "") for value in (
        mission.get("title"), mission.get("raw_text"), mission.get("selected_next_step"),
        packet.get("summary"), packet.get("blocked_reason"),
    )).lower()
    flags.extend(f"protected_term:{term}" for term in sorted(PROTECTED_TERMS) if term in text)
    governance = packet.get("mission_governance_decision") if isinstance(packet.get("mission_governance_decision"), dict) else {}
    if governance.get("red_zone_findings"):
        flags.append("red_zone_findings")
    return list(dict.fromkeys(flags))


def _decision(allowed, reason, **extra):
    return {"version": "charlie_delegated_governance_v1", "allowed": allowed, "reason": reason, **extra}
