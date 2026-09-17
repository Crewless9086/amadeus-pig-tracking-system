"""Authoritative owner-review readiness rules for CHARLIE missions."""

PASSING_CHECK_CONCLUSIONS = {"SUCCESS", "SKIPPED", "NEUTRAL"}
TERMINAL_DEPENDENCY_STATUSES = {"done", "merged", "deployed"}


def validate_review_readiness(mission, pr_state, dependency_states=None, release_base="main"):
    mission = mission if isinstance(mission, dict) else {}
    pr_state = pr_state if isinstance(pr_state, dict) else {}
    packet = _review_packet(mission)
    reasons = []
    head_sha = str(pr_state.get("headRefOid") or "").strip()
    base_branch = str(pr_state.get("baseRefName") or "").strip()
    checks = pr_state.get("statusCheckRollup") if isinstance(pr_state.get("statusCheckRollup"), list) else []

    if str(pr_state.get("state") or "").upper() != "OPEN":
        reasons.append("pr_not_open")
    if base_branch != str(release_base or "main").strip():
        reasons.append("wrong_release_base")
    if str(pr_state.get("mergeable") or "").upper() != "MERGEABLE":
        reasons.append("pr_not_mergeable")
    if not checks or any(_check_conclusion(item) not in PASSING_CHECK_CONCLUSIONS for item in checks):
        reasons.append("checks_not_green")
    if not head_sha:
        reasons.append("head_revision_missing")

    tested_revision = str(
        packet.get("tested_revision")
        or (packet.get("github_reconciliation") or {}).get("head_sha")
        or head_sha
    ).strip()
    if not tested_revision or tested_revision != head_sha:
        reasons.append("tested_revision_mismatch")

    recommendation = str(packet.get("recommended_owner_decision") or "approve_final_release").strip().lower()
    if recommendation not in {"approve", "approve_final", "approve_final_release"}:
        reasons.append("owner_approval_not_recommended")
    reasons.extend(_review_finding_reasons(packet, head_sha))

    governance = (mission.get("metadata") or {}).get("mission_governance") if isinstance(mission.get("metadata"), dict) else {}
    matrix = governance.get("acceptance_matrix") if isinstance(governance, dict) and isinstance(governance.get("acceptance_matrix"), list) else []
    if matrix and any(str(row.get("status") or "pending").lower() not in {"pass", "passed", "complete", "completed"} for row in matrix if isinstance(row, dict)):
        reasons.append("acceptance_matrix_incomplete")

    if _mission_ui_related(mission):
        visual = packet.get("visual_review") if isinstance(packet.get("visual_review"), dict) else {}
        if not visual.get("media") and visual.get("status") not in {"captured", "not_applicable"}:
            reasons.append("visual_evidence_missing")

    dependencies = mission_dependency_ids(mission)
    dependency_states = dependency_states if isinstance(dependency_states, dict) else {}
    incomplete_dependencies = [
        dependency_id for dependency_id in dependencies
        if str(dependency_states.get(dependency_id) or "unknown").lower() not in TERMINAL_DEPENDENCY_STATUSES
    ]
    if incomplete_dependencies:
        reasons.append("dependencies_incomplete")

    return {
        "passed": not reasons,
        "reasons": list(dict.fromkeys(reasons)),
        "head_sha": head_sha,
        "tested_revision": tested_revision,
        "base_branch": base_branch,
        "release_base": release_base,
        "dependencies": dependencies,
        "incomplete_dependencies": incomplete_dependencies,
    }


def mission_dependency_ids(mission):
    metadata = mission.get("metadata") if isinstance(mission, dict) and isinstance(mission.get("metadata"), dict) else {}
    family = metadata.get("mission_family") if isinstance(metadata.get("mission_family"), dict) else {}
    values = metadata.get("depends_on_mission_ids") or []
    values = values if isinstance(values, list) else [values]
    if family.get("dependency"):
        values.append(family["dependency"])
    return list(dict.fromkeys(str(value).strip() for value in values if str(value or "").strip()))


def mission_execution_dependency_ids(mission):
    """Return true prerequisites, excluding the parent a recovery slice repairs."""
    dependencies = mission_dependency_ids(mission)
    metadata = mission.get("metadata") if isinstance(mission, dict) and isinstance(mission.get("metadata"), dict) else {}
    family = metadata.get("mission_family") if isinstance(metadata.get("mission_family"), dict) else {}
    relationship = str(family.get("relationship") or family.get("discovery_source") or "").strip().lower()
    if relationship not in {"acceptance_recovery", "internal_recovery", "block_recovery"}:
        return dependencies
    parent_id = str(family.get("parent_mission_id") or "").strip()
    return [dependency_id for dependency_id in dependencies if dependency_id != parent_id]


def cleared_review_packet(packet, *, reason, return_to_stage):
    packet = dict(packet if isinstance(packet, dict) else {})
    packet.update({
        "review_status": "internal_recovery_queued",
        "blocked_agent": "",
        "blocked_reason": "",
        "unresolved_blockers": [],
        "recommended_owner_decision": "",
        "return_to_stage": return_to_stage,
        "recommended_next_action": f"CORE will recover at {return_to_stage}: {reason}.",
    })
    return packet


def _review_packet(mission):
    metadata = mission.get("metadata") if isinstance(mission.get("metadata"), dict) else {}
    return metadata.get("review_packet") if isinstance(metadata.get("review_packet"), dict) else {}


def _mission_ui_related(mission):
    metadata = mission.get("metadata") if isinstance(mission.get("metadata"), dict) else {}
    core = metadata.get("charlie_core") if isinstance(metadata.get("charlie_core"), dict) else {}
    truth = core.get("project_truth") if isinstance(core.get("project_truth"), dict) else {}
    return str(truth.get("workflow_template") or "").strip() == "ui_product_build"


def _review_finding_reasons(packet, head_sha):
    """Use candidate-bound evidence when available; retain strict legacy behavior."""
    reconciliation = packet.get("evidence_reconciliation") if isinstance(packet.get("evidence_reconciliation"), dict) else {}
    if not reconciliation.get("version"):
        return ["unresolved_review_findings"] if (
            packet.get("errors") or packet.get("bugs") or packet.get("unresolved_blockers")
        ) else []

    reasons = []
    manifest = reconciliation.get("candidate_manifest") if isinstance(reconciliation.get("candidate_manifest"), dict) else {}
    candidate_revision = str(manifest.get("source_commit") or "").strip()
    if candidate_revision and head_sha and candidate_revision != head_sha:
        reasons.append("candidate_revision_mismatch")
    if reconciliation.get("active_blockers"):
        reasons.append("unresolved_review_findings")
    if reconciliation.get("requires_revalidation"):
        reasons.append("evidence_revalidation_required")
    return reasons


def _check_conclusion(item):
    if not isinstance(item, dict):
        return ""
    return str(item.get("conclusion") or item.get("state") or item.get("status") or "").strip().upper()
