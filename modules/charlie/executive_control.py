"""Deterministic CHARLIE executive policy and portfolio decisions."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone


RED_ZONE_TERMS = {
    "customer_send", "public_post", "payment", "deposit", "reservation",
    "stock_write", "lifecycle_write", "purpose_write", "destructive_migration",
    "production_delete", "credential_access",
}
RECOVERABLE_CLASSES = {
    "system_repair_required", "environment_retry_required", "branch_repair_required",
    "implementation_fix_required", "evidence_repair_required",
    "stale_state_reconciliation_required",
}
TERMINAL_STATUSES = {"done", "merged", "deployed", "rejected", "cancelled"}


def authority_decision(capability, policies, *, risk_flags=None, trust=None, now=None):
    risk_flags = {str(item).strip().lower() for item in (risk_flags or []) if str(item).strip()}
    if risk_flags & RED_ZONE_TERMS:
        return _decision(False, "charl_human", "red_zone_owner_approval_required")
    now = now or datetime.now(timezone.utc)
    candidates = [
        item for item in (policies or [])
        if isinstance(item, dict)
        and item.get("capability") == capability
        and item.get("enabled") is True
        and _not_expired(item.get("expires_at"), now)
    ]
    if not candidates:
        return _decision(False, "charl_human", "delegation_policy_missing")
    policy = sorted(candidates, key=lambda item: _tier_rank(item.get("authority_tier")))[0]
    tier = str(policy.get("authority_tier") or "charl_human")
    if tier == "charl_human":
        return _decision(False, tier, "policy_requires_human", policy)
    if tier == "charlie_delegated" and trust is not None:
        trust_row = next((row for row in trust if isinstance(row, dict) and row.get("capability_key") == capability), {})
        if trust_row.get("tier") not in {"delegated", "auto"}:
            return _decision(False, "charl_human", "capability_trust_not_promoted", policy)
    return _decision(True, tier, "delegation_policy_allows", policy)


def recovery_decision(mission, policies, *, trust=None, now=None):
    from modules.charlie.block_adjudication import adjudicate_block

    mission = mission if isinstance(mission, dict) else {}
    adjudication = adjudicate_block(mission)
    block_class = str(adjudication.get("block_class") or "").strip()
    if adjudication.get("action") == "none":
        return adjudication
    if adjudication.get("owner_required"):
        metadata = mission.get("metadata") if isinstance(mission.get("metadata"), dict) else {}
        packet = metadata.get("review_packet") if isinstance(metadata.get("review_packet"), dict) else {}
        reason = str(adjudication.get("reason") or packet.get("blocked_reason") or "A genuine owner decision is required.")
        return {
            "action": "escalate_owner", "reason": "genuine_owner_decision_required",
            "block_class": block_class or "unclassified", "authority_tier": "charl_human",
            "title": mission.get("title") or mission.get("mission_id"),
            "requested_authority": _requested_owner_authority(reason),
            "decision_context": reason,
            "recommended_action": str(packet.get("recommended_next_action") or "Review the stated protected decision; approve only if the business outcome is intended."),
            "if_approved": "CHARLIE will re-read current state and continue the bounded mission through the existing safe executor.",
            "if_declined": "The protected action remains unchanged; CHARLIE will preserve evidence and continue unrelated work.",
            "private_text": f"{mission.get('title') or mission.get('mission_id')} needs one genuine owner decision: {reason}",
        }
    authority = authority_decision("core.internal_recovery", policies, trust=trust, now=now)
    if not authority["allowed"]:
        return {"action": "escalate_owner", "block_class": block_class, **authority}
    target = adjudication.get("target_stage") or "planner"
    fingerprint = adjudication.get("fingerprint")
    action = {"recover_stage": "schedule_recovery", "decompose_acceptance": "decompose_acceptance", "reconcile_pr": "reconcile_pr"}.get(adjudication.get("action"), adjudication.get("action"))
    return {
        **adjudication, "action": action, "capability": "core.internal_recovery",
        "authority_tier": authority["authority_tier"], "policy_id": authority.get("policy_id", ""),
        "target_stage": target, "block_class": block_class, "fingerprint": fingerprint,
        "idempotency_key": f"{action}:{mission.get('mission_id')}:{fingerprint}",
    }


def portfolio_priority(mission, *, active_goal_ids=None):
    mission = mission if isinstance(mission, dict) else {}
    metadata = mission.get("metadata") if isinstance(mission.get("metadata"), dict) else {}
    queue = metadata.get("queue") if isinstance(metadata.get("queue"), dict) else {}
    family = metadata.get("mission_family") if isinstance(metadata.get("mission_family"), dict) else {}
    urgency = str(mission.get("urgency") or "P2").upper()
    score = {"P0": 100, "P1": 75, "P2": 50, "P3": 25}.get(urgency, 40)
    score += min(20, int(queue.get("business_value") or 0))
    score += min(15, int(queue.get("revenue_impact") or 0))
    if family.get("dependency"):
        score -= 20
    if mission.get("status") == "approved":
        score += 10
    goal_id = str(metadata.get("goal_id") or "")
    if goal_id and goal_id in set(active_goal_ids or []):
        score += 15
    return max(0, min(150, score))


def build_executive_cycle(missions, policies, *, runner=None, goals=None, trust=None, now=None):
    from modules.charlie.delegated_governance import delegated_review_assessment, queue_candidate_assessment
    from modules.charlie.review_readiness import mission_execution_dependency_ids

    now = now or datetime.now(timezone.utc)
    missions = [item for item in (missions or []) if isinstance(item, dict)]
    goals = [item for item in (goals or []) if isinstance(item, dict) and item.get("status") == "active"]
    active_goal_ids = [item.get("goal_id") for item in goals]
    commands = []
    escalations = []
    children_by_parent = {}
    for item in missions:
        family = ((item.get("metadata") or {}).get("mission_family") or {}) if isinstance(item.get("metadata"), dict) else {}
        parent_id = str(family.get("parent_mission_id") or "").strip()
        if parent_id:
            children_by_parent.setdefault(parent_id, []).append(item)
    for mission in missions:
        if mission.get("status") == "blocked":
            decision = recovery_decision(mission, policies, trust=trust, now=now)
            target = commands if decision.get("action") in {"schedule_recovery", "decompose_acceptance", "reconcile_pr"} else escalations
            target.append({"mission_id": mission.get("mission_id"), **decision})
        elif mission.get("status") == "pr_ready":
            assessment = delegated_review_assessment(mission)
            if assessment.get("allowed"):
                authority = authority_decision("core.review_delegate", policies, trust=trust, now=now)
                if authority.get("allowed"):
                    fingerprint = stable_fingerprint({
                        "mission_id": mission.get("mission_id"), "review": assessment,
                        "retry_window": now.strftime("%Y%m%d%H"),
                    })
                    commands.append({
                        "action": "verify_and_delegate_review", "capability": "core.review_delegate",
                        "mission_id": mission.get("mission_id"), "assessment": assessment,
                        "authority_tier": authority["authority_tier"], "policy_id": authority.get("policy_id", ""),
                        "idempotency_key": f"delegate-review:{mission.get('mission_id')}:{fingerprint}",
                    })
            elif assessment.get("reason") == "protected_surface_requires_owner":
                metadata = mission.get("metadata") if isinstance(mission.get("metadata"), dict) else {}
                packet = metadata.get("review_packet") if isinstance(metadata.get("review_packet"), dict) else {}
                review_generation = stable_fingerprint({
                    "mission_id": mission.get("mission_id"),
                    "tested_revision": packet.get("tested_revision") or packet.get("current_revision") or "",
                    "pr_url": packet.get("pr_url") or metadata.get("pr_url") or "",
                    "risk_flags": assessment.get("risk_flags", []),
                })
                escalations.append({
                    "action": "review_owner_required", "mission_id": mission.get("mission_id"),
                    "mission_status": "pr_ready",
                    "title": mission.get("title") or mission.get("mission_id"),
                    "reason": assessment.get("reason"), "risk_flags": assessment.get("risk_flags", []),
                    "recommended_action": "Review the protected change and explicitly approve or send it back.",
                    "authority_tier": "charl_human", "block_class": "protected_review",
                    "notification_fingerprint": review_generation,
                })
        elif mission.get("status") == "paused":
            children = children_by_parent.get(str(mission.get("mission_id") or ""), [])
            if children and all(str(child.get("status") or "").lower() in TERMINAL_STATUSES for child in children):
                authority = authority_decision("core.internal_recovery", policies, trust=trust, now=now)
                if authority.get("allowed"):
                    child_state = {str(child.get("mission_id")): str(child.get("status")) for child in children}
                    fingerprint = stable_fingerprint(child_state)
                    commands.append({
                        "action": "reconcile_family", "capability": "core.internal_recovery",
                        "mission_id": mission.get("mission_id"), "child_states": child_state,
                        "authority_tier": authority["authority_tier"], "policy_id": authority.get("policy_id", ""),
                        "idempotency_key": f"family-reconcile:{mission.get('mission_id')}:{fingerprint}",
                    })
    status_by_id = {str(item.get("mission_id") or ""): str(item.get("status") or "").lower() for item in missions}
    approved = [item for item in missions if item.get("status") == "approved"]
    runnable = [item for item in approved if _dependencies_ready(item, status_by_id, mission_execution_dependency_ids)]
    dependency_blocked = [item for item in approved if item not in runnable]
    ranked = sorted(runnable, key=lambda item: (-portfolio_priority(item, active_goal_ids=active_goal_ids), str(item.get("created_at") or "")))
    runner = runner if isinstance(runner, dict) else {}
    if ranked and not runner.get("active_mission_id"):
        queue_authority = authority_decision("core.queue_continue", policies, trust=trust, now=now)
        if queue_authority["allowed"]:
            commands.append({
                "action": "ensure_queue_progress", "capability": "core.queue_continue",
                "mission_id": ranked[0].get("mission_id"),
                "authority_tier": queue_authority["authority_tier"],
                "policy_id": queue_authority.get("policy_id", ""),
                "idempotency_key": f"queue:{ranked[0].get('mission_id')}:{now.date().isoformat()}",
            })
        else:
            escalations.append({"mission_id": ranked[0].get("mission_id"), "action": "queue_progress_not_authorized", **queue_authority})
    runway = len(runnable) + (1 if runner.get("active_mission_id") else 0)
    if runway < 3:
        selection_authority = authority_decision("core.queue_select", policies, trust=trust, now=now)
        candidates = [
            item for item in missions
            if item.get("status") == "new"
            and queue_candidate_assessment(item).get("allowed")
            and _dependencies_ready(item, status_by_id, mission_execution_dependency_ids)
        ]
        candidates = sorted(candidates, key=lambda item: (-portfolio_priority(item, active_goal_ids=active_goal_ids), str(item.get("created_at") or "")))
        if selection_authority.get("allowed"):
            for item in candidates[:3 - runway]:
                fingerprint = stable_fingerprint({"mission_id": item.get("mission_id"), "goal_ids": active_goal_ids, "date": now.date().isoformat()})
                commands.append({
                    "action": "approve_next_work", "capability": "core.queue_select",
                    "mission_id": item.get("mission_id"), "priority_score": portfolio_priority(item, active_goal_ids=active_goal_ids),
                    "authority_tier": selection_authority["authority_tier"], "policy_id": selection_authority.get("policy_id", ""),
                    "idempotency_key": f"queue-select:{item.get('mission_id')}:{fingerprint}",
                })
    if approved and not runnable and not runner.get("active_mission_id"):
        escalations.append({
            "action": "queue_deadlock", "block_class": "queue_dependency_deadlock",
            "authority_tier": "charlie_delegated", "reason": "approved_work_exists_but_none_is_runnable",
            "mission_ids": [item.get("mission_id") for item in dependency_blocked],
            "recommended_action": "CHARLIE must repair dependency semantics or select independent safe work; Charl is not required unless the dependency contains genuine business discretion.",
            "private_text": f"CHARLIE detected a CORE queue deadlock: {len(approved)} approved mission(s), but none can run. I am preserving the queue and escalating the exact dependency chain for automatic repair.",
        })
    return {
        "version": "charlie_executive_cycle_v1", "observed_at": now.isoformat(),
        "mission_count": len(missions), "active_goal_count": len(goals),
        "commands": commands, "escalations": escalations,
        "queue_health": {
            "approved_count": len(approved), "runnable_count": len(runnable),
            "dependency_blocked_count": len(dependency_blocked),
            "dependency_blocked_ids": [item.get("mission_id") for item in dependency_blocked],
            "deadlocked": bool(approved and not runnable and not runner.get("active_mission_id")),
        },
        "queue_rank": [{"mission_id": item.get("mission_id"), "score": portfolio_priority(item, active_goal_ids=active_goal_ids)} for item in ranked],
        "status_counts": {
            status: sum(1 for item in missions if str(item.get("status") or "").lower() == status)
            for status in ("new", "approved", "in_progress", "blocked", "pr_ready", "release_approved", "paused")
        },
    }


def _dependencies_ready(mission, status_by_id, dependency_loader):
    return all(status_by_id.get(dependency_id) in TERMINAL_STATUSES for dependency_id in dependency_loader(mission))


def capability_tier(metrics):
    metrics = metrics if isinstance(metrics, dict) else {}
    runs = int(metrics.get("runs") or 0)
    clean = int(metrics.get("clean_passes") or 0)
    defects = int(metrics.get("escaped_defects") or 0)
    rollbacks = int(metrics.get("rollbacks") or 0)
    if runs < 10 or defects or rollbacks:
        return "watch"
    rate = clean / runs if runs else 0
    if runs >= 50 and rate >= 0.98:
        return "auto"
    if runs >= 20 and rate >= 0.95:
        return "delegated"
    if rate >= 0.90:
        return "queue"
    return "watch"


def stable_fingerprint(value):
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:24]


def _review_packet(mission):
    metadata = mission.get("metadata") if isinstance(mission.get("metadata"), dict) else {}
    return metadata.get("review_packet") if isinstance(metadata.get("review_packet"), dict) else {}


def _decision(allowed, tier, reason, policy=None):
    policy = policy if isinstance(policy, dict) else {}
    return {"allowed": allowed, "authority_tier": tier, "reason": reason, "policy_id": policy.get("policy_id", "")}


def _tier_rank(value):
    return {"auto": 0, "charlie_delegated": 1, "charl_human": 2}.get(str(value), 3)


def _not_expired(value, now):
    if not value:
        return True
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed > now
    except ValueError:
        return False


def _requested_owner_authority(reason):
    text = str(reason or "").lower()
    for label, needles in (
        ("apply_production_migration", ("apply migration", "production migration", "schema change in production")),
        ("customer_send", ("customer send", "send to customer")),
        ("public_post", ("public post",)),
        ("payment_or_deposit", ("payment", "deposit")),
        ("reservation", ("reservation", "reserve stock")),
        ("destructive_production_change", ("destructive", "production data deletion", "delete production")),
    ):
        if any(needle in text for needle in needles):
            return label
    return "material_owner_decision"
