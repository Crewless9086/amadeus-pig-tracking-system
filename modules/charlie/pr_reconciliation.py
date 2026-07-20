"""Reconcile CHARLIE mission state with authoritative GitHub PR state."""

import json
import re
import subprocess

from modules.charlie.block_recovery import classify_block
from modules.charlie.review_readiness import validate_review_readiness


PASSING_CHECK_CONCLUSIONS = {"SUCCESS", "SKIPPED", "NEUTRAL"}


def query_pr_state(pr_reference, run_subprocess=None):
    reference = str(pr_reference or "").strip()
    if not reference:
        return {"success": False, "status": "pr_reference_missing"}
    runner = run_subprocess or subprocess.run
    command = [
        "gh", "pr", "view", reference,
        "--json", "number,url,state,mergeable,baseRefName,headRefName,headRefOid,statusCheckRollup",
    ]
    try:
        completed = runner(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"success": False, "status": "pr_query_failed", "error_type": exc.__class__.__name__}
    if completed.returncode != 0:
        return {"success": False, "status": "pr_query_failed", "returncode": completed.returncode}
    try:
        payload = json.loads(completed.stdout or "{}")
    except json.JSONDecodeError:
        return {"success": False, "status": "pr_query_invalid_json"}
    return {"success": True, "status": "ok", **payload}


def reconciliation_decision(mission, pr_state, dependency_states=None, release_base="main"):
    mission = mission if isinstance(mission, dict) else {}
    pr_state = pr_state if isinstance(pr_state, dict) else {}
    if not pr_state.get("success"):
        return {"action": "none", "reason": pr_state.get("status", "pr_state_unavailable")}
    state = str(pr_state.get("state") or "").upper()
    mergeable = str(pr_state.get("mergeable") or "").upper()
    checks = pr_state.get("statusCheckRollup") if isinstance(pr_state.get("statusCheckRollup"), list) else []
    checks_complete = bool(checks) and all(_check_conclusion(item) in PASSING_CHECK_CONCLUSIONS for item in checks)
    checks_failed = any(_check_conclusion(item) not in PASSING_CHECK_CONCLUSIONS | {"", "PENDING", "IN_PROGRESS", "QUEUED"} for item in checks)
    review_packet = _review_packet(mission)
    ui_related = _mission_ui_related(mission)
    visual = review_packet.get("visual_review") if isinstance(review_packet.get("visual_review"), dict) else {}
    visual_ready = not ui_related or bool(visual.get("media")) or visual.get("status") in {"captured", "not_applicable"}
    head_sha = str(pr_state.get("headRefOid") or "").strip()

    if state == "MERGED":
        return {"action": "mark_merged", "target_status": "merged", "reason": "github_pr_merged", "head_sha": head_sha}
    if state != "OPEN":
        return {"action": "none", "reason": f"github_pr_state_{state.lower() or 'unknown'}", "head_sha": head_sha}
    readiness = validate_review_readiness(mission, pr_state, dependency_states, release_base)
    if "wrong_release_base" in readiness["reasons"]:
        disposition = classify_block("publisher", "GitHub PR targets the wrong branch and must be rebased onto the release base.", review_packet)
        return {"action": "queue_recovery", "target_status": "approved", "reason": "github_pr_wrong_release_base", "disposition": disposition, "head_sha": head_sha, "readiness": readiness}
    if "dependencies_incomplete" in readiness["reasons"]:
        disposition = classify_block("planner", "Mission dependencies are not complete.", review_packet)
        return {"action": "wait_dependencies", "target_status": "approved", "reason": "mission_dependencies_incomplete", "disposition": disposition, "head_sha": head_sha, "readiness": readiness}
    if mergeable == "CONFLICTING":
        disposition = classify_block("publisher", "GitHub PR has merge conflicts.", review_packet)
        return {"action": "queue_recovery", "target_status": "approved", "reason": "github_pr_conflicting", "disposition": disposition, "head_sha": head_sha}
    if checks_failed:
        disposition = classify_block("tester", "Current PR checks failed for the current diff.", {"introduced_by_current_diff": True})
        return {"action": "queue_recovery", "target_status": "approved", "reason": "github_checks_failed", "disposition": disposition, "head_sha": head_sha}
    if checks_complete and mergeable == "MERGEABLE" and not visual_ready:
        disposition = classify_block("visual_qa_reviewer", "Visual review media was not captured.", review_packet)
        return {"action": "queue_recovery", "target_status": "approved", "reason": "visual_evidence_required", "disposition": disposition, "head_sha": head_sha}
    if checks_complete and mergeable == "MERGEABLE" and visual_ready and readiness["passed"]:
        return {"action": "mark_pr_ready", "target_status": "pr_ready", "reason": "github_pr_green_and_reviewable", "head_sha": head_sha, "readiness": readiness}
    if checks_complete and mergeable == "MERGEABLE" and visual_ready:
        blocked_agent = str(review_packet.get("blocked_agent") or "").strip()
        blocked_reason = str(review_packet.get("blocked_reason") or "").strip()
        if (
            str(mission.get("status") or "").strip().lower() == "blocked"
            and str(review_packet.get("review_status") or "").strip() == "workflow_not_ready"
            and blocked_agent
        ):
            # Preserve the exact stage identified by the execution gate. The
            # generic readiness summary otherwise routes every retry through
            # evidence_reviewer while the actual stale stage never refreshes.
            disposition = classify_block(blocked_agent, blocked_reason or "Targeted workflow evidence recheck required.", review_packet)
            disposition["responsible_stage"] = blocked_agent
            return {
                "action": "queue_recovery",
                "target_status": "approved",
                "reason": "owner_review_targeted_recheck",
                "disposition": disposition,
                "head_sha": head_sha,
                "readiness": readiness,
            }
        disposition = classify_block("evidence_reviewer", "Owner review readiness evidence is incomplete: " + ", ".join(readiness["reasons"]), review_packet)
        return {"action": "queue_recovery", "target_status": "approved", "reason": "owner_review_readiness_incomplete", "disposition": disposition, "head_sha": head_sha, "readiness": readiness}
    return {"action": "none", "reason": "github_checks_pending_or_mergeability_unknown", "head_sha": head_sha}


def mission_pr_reference(mission):
    packet = _review_packet(mission)
    links = packet.get("links") if isinstance(packet.get("links"), dict) else {}
    for value in (packet.get("pr_url"), links.get("pr"), links.get("pull_request")):
        if str(value or "").strip():
            return str(value).strip()
    text = json.dumps(packet)
    match = re.search(r"https://github\.com/[^\s\"']+/pull/\d+", text)
    return match.group(0) if match else ""


def _review_packet(mission):
    metadata = mission.get("metadata") if isinstance(mission.get("metadata"), dict) else {}
    return metadata.get("review_packet") if isinstance(metadata.get("review_packet"), dict) else {}


def _mission_ui_related(mission):
    metadata = mission.get("metadata") if isinstance(mission.get("metadata"), dict) else {}
    core = metadata.get("charlie_core") if isinstance(metadata.get("charlie_core"), dict) else {}
    truth = core.get("project_truth") if isinstance(core.get("project_truth"), dict) else {}
    return str(truth.get("workflow_template") or "").strip() == "ui_product_build"


def _check_conclusion(item):
    if not isinstance(item, dict):
        return ""
    return str(item.get("conclusion") or item.get("state") or item.get("status") or "").strip().upper()
