"""Semantic adjudication for blocked CHARLIE missions.

The adjudicator separates work CORE can repair from decisions that genuinely
require Charl. Retry exhaustion is evidence that the recovery strategy must
change; it is not owner discretion by itself.
"""

from __future__ import annotations

import re

from modules.charlie.block_recovery import classify_block
from modules.charlie.executive_control import stable_fingerprint
from modules.charlie.pr_reconciliation import mission_pr_reference, reconciliation_decision


OWNER_CLASSES = {"owner_decision_required", "red_zone_owner_approval_required"}
PASS_STATUSES = {"pass", "passed", "complete", "completed"}


def adjudicate_block(mission, *, pr_state=None, dependency_states=None):
    mission = mission if isinstance(mission, dict) else {}
    if mission.get("status") != "blocked":
        return {"action": "none", "reason": "mission_not_blocked", "owner_required": False}
    packet = _packet(mission)
    if str(packet.get("review_status") or "").strip() == "system_incident_halted":
        return {
            "version": "charlie_block_adjudication_v1",
            "action": "system_incident_halted",
            "owner_required": False,
            "block_class": "system_incident_halted",
            "target_stage": str(packet.get("blocked_agent") or "evidence_reviewer"),
            "reason": str(packet.get("blocked_reason") or "Repeated recovery halted."),
            "fingerprint": str((packet.get("owner_review_gate_failure") or {}).get("fingerprint") or ""),
        }
    reason = str(packet.get("blocked_reason") or packet.get("summary") or mission.get("owner_decision") or "").strip()
    stored = packet.get("block_disposition") if isinstance(packet.get("block_disposition"), dict) else {}
    disposition = classify_block(str(packet.get("blocked_agent") or ""), reason, packet)
    pending = pending_acceptance_rows(mission)
    exhaustion = _contains(reason, ("bounded correction budget", "frozen acceptance criteria", "recovery attempts exhausted", "repeated same blocker loop", "durable loop cap"))

    # Exhausted implementation work changes strategy. It is not discretion,
    # even when an older governance packet labelled the exhausted route owner_block.
    if exhaustion and len(pending) >= 3 and disposition.get("block_class") != "red_zone_owner_approval_required":
        internal = classify_block(str(packet.get("blocked_agent") or "builder"), reason, {})
        return _result(mission, "decompose_acceptance", internal, reason, pending_rows=pending)

    # Only explicit red-zone language or actual owner discretion may wake Charl.
    if disposition.get("block_class") == "red_zone_owner_approval_required" or (
        disposition.get("block_class") == "owner_decision_required" and _genuine_owner_reason(reason)
    ):
        return _result(mission, "escalate_owner", disposition, reason)
    if disposition.get("block_class") == "owner_decision_required":
        neutral_packet = dict(packet)
        neutral_packet.pop("mission_governance_decision", None)
        disposition = classify_block(str(packet.get("blocked_agent") or "builder"), reason, neutral_packet)

    pr_reference = mission_pr_reference(mission)
    if pr_reference:
        if pr_state is None:
            return _result(mission, "reconcile_pr", disposition, reason, pr_reference=pr_reference)
        pr_decision = reconciliation_decision(
            mission, pr_state, dependency_states=dependency_states,
        )
        if pr_decision.get("action") in {"mark_pr_ready", "mark_merged"}:
            action = "reconcile_pr_ready" if pr_decision["action"] == "mark_pr_ready" else "reconcile_merged"
            return _result(mission, action, disposition, pr_decision.get("reason", reason), pr_reference=pr_reference, pr_decision=pr_decision)
        if pr_decision.get("action") == "queue_recovery":
            if _stale_legacy_packet_is_superseded(packet, reason, pr_state, pr_decision):
                reconciled = {
                    "action": "mark_pr_ready", "target_status": "pr_ready",
                    "reason": "authoritative_green_pr_supersedes_stale_legacy_block",
                    "head_sha": pr_state.get("headRefOid"),
                }
                return _result(mission, "reconcile_pr_ready", disposition, reconciled["reason"], pr_reference=pr_reference, pr_decision=reconciled)
            pr_disposition = pr_decision.get("disposition") or disposition
            return _result(mission, "recover_stage", pr_disposition, pr_decision.get("reason", reason), pr_reference=pr_reference, pr_decision=pr_decision)

    # Reclassify legacy packets that called retry exhaustion an owner block.
    if stored.get("block_class") in OWNER_CLASSES and not disposition.get("owner_required"):
        stored = disposition
    target = str(disposition.get("responsible_stage") or packet.get("return_to_stage") or "planner").strip()
    return _result(mission, "recover_stage", stored or disposition, reason, target_stage=target)


def pending_acceptance_rows(mission):
    metadata = mission.get("metadata") if isinstance(mission.get("metadata"), dict) else {}
    governance = metadata.get("mission_governance") if isinstance(metadata.get("mission_governance"), dict) else {}
    rows = governance.get("acceptance_matrix") if isinstance(governance.get("acceptance_matrix"), list) else []
    return [dict(row) for row in rows if isinstance(row, dict) and str(row.get("status") or "pending").lower() not in PASS_STATUSES]


def _result(mission, action, disposition, reason, **extra):
    block_class = str(disposition.get("block_class") or "system_repair_required")
    target = str(extra.get("target_stage") or disposition.get("responsible_stage") or "planner")
    fingerprint = stable_fingerprint({
        "mission_id": mission.get("mission_id"), "action": action,
        "block_class": block_class, "target": target, "reason": _canonical_block_reason(reason),
        "pending": [row.get("id") for row in extra.get("pending_rows", [])],
    })
    return {
        "version": "charlie_block_adjudication_v1", "action": action,
        "owner_required": action == "escalate_owner", "block_class": block_class,
        "target_stage": target, "reason": reason, "fingerprint": fingerprint,
        "idempotency_key": f"adjudicate:{mission.get('mission_id')}:{fingerprint}",
        **extra,
    }


def _canonical_block_reason(reason):
    """Keep retry fingerprints stable when recovery wraps the same cause."""
    value = str(reason or "").strip().lower()
    value = re.sub(
        r"^repeated internal recovery stopped after \d+ identical occurrences:\s*",
        "",
        value,
    )
    value = re.sub(r"\b[a-f0-9]{8}-\d{8}t\d{6}z-\d{6,}\b", "<execution>", value)
    return " ".join(value.split())


def _packet(mission):
    metadata = mission.get("metadata") if isinstance(mission.get("metadata"), dict) else {}
    return metadata.get("review_packet") if isinstance(metadata.get("review_packet"), dict) else {}


def _contains(text, needles):
    value = str(text or "").lower()
    return any(needle in value for needle in needles)


def _genuine_owner_reason(reason):
    return _contains(reason, (
        "owner must decide", "owner decision required", "needs owner decision",
        "missing owner decision", "business choice", "ambiguous owner intent",
        "choose between", "pricing decision", "commercial decision",
    ))


def _stale_legacy_packet_is_superseded(packet, reason, pr_state, pr_decision):
    reconciliation = packet.get("evidence_reconciliation") if isinstance(packet.get("evidence_reconciliation"), dict) else {}
    if reconciliation.get("version"):
        return False
    checks = pr_state.get("statusCheckRollup") if isinstance(pr_state.get("statusCheckRollup"), list) else []
    green = bool(checks) and all(str(item.get("conclusion") or item.get("state") or "").upper() in {"SUCCESS", "SKIPPED", "NEUTRAL"} for item in checks if isinstance(item, dict))
    stale_reason = _contains(reason, ("conflict", "branch", "check", "pr #", "pull request", "stale", "revalidation"))
    readiness = pr_decision.get("readiness") if isinstance(pr_decision.get("readiness"), dict) else {}
    allowed_reasons = {"unresolved_review_findings", "owner_approval_not_recommended", "tested_revision_mismatch"}
    return (
        green
        and str(pr_state.get("state") or "").upper() == "OPEN"
        and str(pr_state.get("mergeable") or "").upper() == "MERGEABLE"
        and stale_reason
        and set(readiness.get("reasons") or []).issubset(allowed_reasons)
    )
