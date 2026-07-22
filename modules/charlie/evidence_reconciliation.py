import hashlib
import json
from datetime import datetime, timezone


EVIDENCE_RECONCILIATION_VERSION = "charlie_evidence_reconciliation_v1"
FINDING_STATES = {"open", "resolved", "superseded", "accepted_risk", "follow_up", "owner_decision_required"}
PASS_RESULTS = {"pass", "passed", "complete", "completed", "approve", "approve_final_release", "mark_done", "ready"}
FAIL_RESULTS = {"fail", "failed", "blocked", "send_back", "pause", "reject"}
RELEASE_REVIEW_AGENTS = {
    "tester", "qa_red_team", "product_reviewer", "business_reviewer",
    "security_reviewer", "evidence_reviewer", "visual_qa_reviewer", "reviewer", "publisher",
}
SCOPE_PLANNING_AGENTS = {
    "idea_expander", "source_mapper", "product_architect", "technical_architect",
    "business_model_agent", "council_synthesis", "planner", "architect",
}


def build_candidate_manifest(mission, artifacts=None, source_commit=""):
    mission = mission if isinstance(mission, dict) else {}
    artifacts = artifacts if isinstance(artifacts, dict) else {}
    source_commit = _clean(source_commit) or _artifact_revision(artifacts.get("builder"))
    if not source_commit:
        source_commit = _latest_artifact_revision(artifacts)
    changed_files = sorted({
        _clean(path).replace("\\", "/")
        for artifact in artifacts.values() if isinstance(artifact, dict)
        for path in _list(artifact.get("changed_files"))
        if _clean(path)
    })
    metadata = mission.get("metadata") if isinstance(mission.get("metadata"), dict) else {}
    vault = mission.get("vault") if isinstance(mission.get("vault"), dict) else {}
    governance = metadata.get("mission_governance") if isinstance(metadata.get("mission_governance"), dict) else {}
    matrix = governance.get("acceptance_matrix") if isinstance(governance.get("acceptance_matrix"), list) else []
    frozen_criteria = [
        _clean(row.get("requirement"))
        for row in matrix if isinstance(row, dict) and _clean(row.get("requirement"))
    ] if governance.get("matrix_frozen") else []
    criteria = frozen_criteria or vault.get("acceptance_criteria") or metadata.get("acceptance_criteria") or []
    required = vault.get("required_artifacts") or metadata.get("required_artifacts") or []
    authority = metadata.get("authority_flags") if isinstance(metadata.get("authority_flags"), dict) else {}
    scope_payload = {
        "mission_id": _clean(mission.get("mission_id")),
        "title": _clean(mission.get("title")),
        "criteria": _list(criteria),
        "required_artifacts": _list(required),
    }
    scope_hash = _digest(scope_payload)
    scope_source = "frozen_governance" if frozen_criteria else "mission_metadata"
    # A mission already in flight may have candidate-bound evidence produced
    # by the pre-governance scope algorithm. Preserve that exact candidate's
    # established scope instead of invalidating every passing release artifact
    # merely because CORE itself was upgraded during review.
    established_scopes = {}
    if source_commit:
        for artifact in artifacts.values():
            if not isinstance(artifact, dict) or _artifact_revision(artifact) != source_commit:
                continue
            lineage = artifact.get("evidence_lineage") if isinstance(artifact.get("evidence_lineage"), dict) else {}
            established = _clean(lineage.get("scope_hash") or artifact.get("scope_hash"))
            if established:
                established_scopes[established] = established_scopes.get(established, 0) + 1
    if established_scopes:
        scope_hash = sorted(established_scopes, key=lambda value: (-established_scopes[value], value))[0]
        scope_source = "established_exact_candidate"
    candidate_payload = {"source_commit": source_commit, "scope_hash": scope_hash, "changed_files": changed_files}
    return {
        "version": EVIDENCE_RECONCILIATION_VERSION,
        "mission_id": _clean(mission.get("mission_id")),
        "source_commit": source_commit,
        "scope_hash": scope_hash,
        "scope_source": scope_source,
        "candidate_fingerprint": _digest(candidate_payload),
        "changed_files": changed_files,
        "acceptance_criteria": _list(criteria),
        "required_artifacts": _list(required),
        "authority_flags": authority,
        "created_at": _now(),
    }


def bind_artifact_to_candidate(artifact, agent, execution_id, attempt, manifest, previous_artifact=None):
    artifact = dict(artifact if isinstance(artifact, dict) else {})
    manifest = manifest if isinstance(manifest, dict) else {}
    previous_artifact = previous_artifact if isinstance(previous_artifact, dict) else {}
    artifact_id = _digest({
        "agent": _clean(agent), "execution_id": _clean(execution_id), "attempt": int(attempt or 1),
        "candidate": manifest.get("candidate_fingerprint"), "summary": artifact.get("summary"),
    })
    lineage = {
        "version": EVIDENCE_RECONCILIATION_VERSION,
        "artifact_id": artifact_id,
        "agent": _clean(agent).lower(),
        "execution_id": _clean(execution_id),
        "attempt": int(attempt or 1),
        "source_commit": _artifact_revision(artifact) or _clean(manifest.get("source_commit")),
        "candidate_fingerprint": _clean(manifest.get("candidate_fingerprint")),
        "scope_hash": _clean(manifest.get("scope_hash")),
        "created_at": _clean(artifact.get("completed_at")) or _now(),
        "supersedes_artifact_id": _artifact_id(previous_artifact),
    }
    artifact["evidence_lineage"] = lineage
    artifact["artifact_id"] = artifact_id
    artifact["candidate_fingerprint"] = lineage["candidate_fingerprint"]
    artifact["scope_hash"] = lineage["scope_hash"]
    artifact["source_commit"] = lineage["source_commit"]
    artifact["structured_findings"] = normalize_findings(artifact, artifact_id)
    return artifact


def normalize_findings(artifact, artifact_id=""):
    artifact = artifact if isinstance(artifact, dict) else {}
    findings = []
    for kind, key in (("error", "errors"), ("bug", "bugs"), ("risk", "risk_notes"), ("risk", "qa_findings")):
        for item in _list(artifact.get(key)):
            payload = item if isinstance(item, dict) else {"finding": _clean(item)}
            text = _clean(payload.get("finding") or payload.get("summary") or payload.get("message") or item)
            if not text:
                continue
            state = _clean(payload.get("state") or payload.get("status") or "open").lower()
            if state not in FINDING_STATES:
                state = "open"
            findings.append({
                "finding_id": _clean(payload.get("finding_id") or payload.get("id")) or _digest({"kind": kind, "text": text}),
                "kind": kind,
                "state": state,
                "finding": text,
                "severity": _clean(payload.get("severity")),
                "source_artifact_id": artifact_id,
                "resolved_by_artifact_id": _clean(payload.get("resolved_by_artifact_id")),
                "follow_up_mission_id": _clean(payload.get("follow_up_mission_id")),
            })
    return findings


def resolve_effective_agent_results(artifact_history, candidate_manifest, workflow=None, judgement=None):
    candidate_manifest = candidate_manifest if isinstance(candidate_manifest, dict) else {}
    history = _history_by_agent(artifact_history)
    workflow_agents = [
        _clean(item.get("agent")).lower() for item in _list(workflow)
        if isinstance(item, dict) and _clean(item.get("agent"))
    ]
    agents = list(dict.fromkeys([*workflow_agents, *history.keys()]))
    effective = {}
    historical = []
    refresh = []
    active_blockers = []
    resolved_findings = []
    follow_ups = []
    candidate_fp = _clean(candidate_manifest.get("candidate_fingerprint"))
    candidate_commit = _clean(candidate_manifest.get("source_commit"))
    scope_hash = _clean(candidate_manifest.get("scope_hash"))
    planning_scope_bridge = _planning_scope_bridge_agents(history, workflow_agents, scope_hash)
    for agent in agents:
        entries = sorted(history.get(agent, []), key=_artifact_sort_key, reverse=True)
        selected = None
        last_inapplicable_reason = "no_artifact_applies_to_current_candidate"
        for artifact in entries:
            applicable, reason = artifact_applicability(
                artifact, candidate_fp, candidate_commit, scope_hash, agent_name=agent,
                accept_upstream_planning_scope=agent in planning_scope_bridge,
            )
            if applicable and selected is None:
                selected = artifact
                effective[agent] = {"artifact": artifact, "applicability": reason, "artifact_id": _artifact_id(artifact)}
            else:
                if not applicable:
                    last_inapplicable_reason = reason
                historical.append({"agent": agent, "artifact_id": _artifact_id(artifact), "reason": reason if not applicable else "superseded_by_newer_applicable_artifact"})
        if selected is None and entries:
            refresh.append({"agent": agent, "reason": last_inapplicable_reason})
            continue
        if selected is None:
            if agent in workflow_agents:
                refresh.append({"agent": agent, "reason": "missing_required_agent_artifact"})
            continue
        result = judgement(agent, selected) if callable(judgement) else _basic_judgement(selected)
        effective[agent]["judgement"] = result
        for finding in _list(selected.get("structured_findings")):
            if not isinstance(finding, dict):
                continue
            state = finding.get("state")
            if state == "follow_up":
                follow_ups.append(finding)
            elif state in {"resolved", "superseded", "accepted_risk"}:
                resolved_findings.append(finding)
        if not result.get("passed"):
            active_blockers.append({"agent": agent, "artifact_id": _artifact_id(selected), "reason": result.get("reason") or "quality_gate_failed"})
    return {
        "version": EVIDENCE_RECONCILIATION_VERSION,
        "candidate_manifest": candidate_manifest,
        "effective_results": effective,
        "historical_results": historical,
        "active_blockers": active_blockers,
        "resolved_findings": resolved_findings,
        "follow_ups": follow_ups,
        "requires_revalidation": refresh,
        "passed": not active_blockers and not refresh,
        "recommended_action": _recommended_action(active_blockers, refresh),
        "evaluated_at": _now(),
    }


def artifact_applicability(
    artifact,
    candidate_fingerprint,
    candidate_commit,
    scope_hash,
    agent_name="",
    accept_upstream_planning_scope=False,
):
    artifact = artifact if isinstance(artifact, dict) else {}
    lineage = artifact.get("evidence_lineage") if isinstance(artifact.get("evidence_lineage"), dict) else {}
    artifact_fp = _clean(lineage.get("candidate_fingerprint") or artifact.get("candidate_fingerprint"))
    artifact_commit = _artifact_revision(artifact)
    artifact_scope = _clean(lineage.get("scope_hash") or artifact.get("scope_hash"))
    agent = _clean(lineage.get("agent") or artifact.get("agent") or agent_name).lower()
    if artifact_fp and candidate_fingerprint and artifact_fp == candidate_fingerprint:
        return True, "exact_candidate"
    if (
        agent in SCOPE_PLANNING_AGENTS
        and artifact.get("accepted_frozen_scope") is True
        and _basic_judgement(artifact).get("passed")
        and bool(_clean(artifact.get("summary")) or artifact.get("handoff_report"))
    ):
        return True, "accepted_frozen_scope"
    if (
        accept_upstream_planning_scope
        and agent in SCOPE_PLANNING_AGENTS
        and artifact_scope
        and scope_hash
        and artifact_scope != scope_hash
        and not artifact_commit
        and _basic_judgement(artifact).get("passed")
        and bool(_clean(artifact.get("summary")) or artifact.get("handoff_report"))
    ):
        # A later pre-build planning stage can freeze the final scope after
        # earlier discovery stages were recorded.  Once that downstream
        # planning artifact is bound to the current frozen scope, preserve
        # its passing upstream ancestry instead of restarting discovery.
        return True, "accepted_upstream_planning_ancestry"
    if artifact_scope and scope_hash and artifact_scope != scope_hash:
        return False, "different_scope"
    if artifact_scope and scope_hash and artifact_scope == scope_hash and agent in SCOPE_PLANNING_AGENTS:
        return True, "same_frozen_scope"
    if artifact_scope and scope_hash and artifact_scope == scope_hash and agent == "risk_agent":
        judgement = _basic_judgement(artifact)
        if judgement.get("passed"):
            return True, "passing_prebuild_risk_same_scope"
        return False, "prebuild_risk_failure_requires_candidate_recheck"
    if artifact_commit and candidate_commit:
        return (artifact_commit == candidate_commit, "exact_revision" if artifact_commit == candidate_commit else "different_revision")
    if artifact_fp and candidate_fingerprint:
        return False, "different_candidate"
    if (
        agent in SCOPE_PLANNING_AGENTS
        and scope_hash
        and _basic_judgement(artifact).get("passed")
        and bool(_clean(artifact.get("summary")) or artifact.get("handoff_report"))
    ):
        # Pre-lineage planning evidence describes the frozen mission scope, not
        # a mutable release revision.  Accept it for the same still-frozen
        # mission scope instead of manufacturing an endless planning rerun.
        return True, "accepted_legacy_frozen_scope"
    return False, "legacy_unbound_evidence_requires_revalidation"


def _planning_scope_bridge_agents(history, workflow_agents, scope_hash):
    """Return upstream planning agents covered by a later frozen-scope handoff."""
    if not scope_hash:
        return set()
    planning_order = [agent for agent in workflow_agents if agent in SCOPE_PLANNING_AGENTS]
    latest_anchor = -1
    for index, agent in enumerate(planning_order):
        for artifact in history.get(agent, []):
            if not isinstance(artifact, dict) or _artifact_revision(artifact):
                continue
            lineage = artifact.get("evidence_lineage") if isinstance(artifact.get("evidence_lineage"), dict) else {}
            artifact_scope = _clean(lineage.get("scope_hash") or artifact.get("scope_hash"))
            if (
                artifact_scope == scope_hash
                and _basic_judgement(artifact).get("passed")
                and bool(_clean(artifact.get("summary")) or artifact.get("handoff_report"))
            ):
                latest_anchor = max(latest_anchor, index)
    if latest_anchor < 0:
        return set()
    return set(planning_order[:latest_anchor])


def targeted_workflow_return(workflow, target_agent, comments="", preserve_agents=None):
    workflow = [dict(item) for item in _list(workflow) if isinstance(item, dict)]
    target_agent = _clean(target_agent).lower()
    preserve_agents = {_clean(agent).lower() for agent in _list(preserve_agents)}
    for item in workflow:
        agent = _clean(item.get("agent")).lower()
        if agent == target_agent:
            item["status"] = "active"
            item["completed_at"] = None
            item["findings"] = _clean(comments)
        elif agent in preserve_agents and item.get("status") == "complete":
            item["status"] = "complete"
        else:
            item["status"] = "pending"
            item["completed_at"] = None
    return workflow


def applicable_passing_agents(artifacts, candidate_manifest):
    artifacts = artifacts if isinstance(artifacts, dict) else {}
    candidate_manifest = candidate_manifest if isinstance(candidate_manifest, dict) else {}
    preserved = []
    for agent, artifact in artifacts.items():
        if not isinstance(artifact, dict):
            continue
        applicable, _ = artifact_applicability(
            artifact,
            _clean(candidate_manifest.get("candidate_fingerprint")),
            _clean(candidate_manifest.get("source_commit")),
            _clean(candidate_manifest.get("scope_hash")),
        )
        if applicable and _basic_judgement(artifact).get("passed"):
            preserved.append(_clean(agent).lower())
    return preserved


def _history_by_agent(value):
    result = {}
    if isinstance(value, dict):
        for agent, artifacts in value.items():
            items = artifacts if isinstance(artifacts, list) else [artifacts]
            result.setdefault(_clean(agent).lower(), []).extend(item for item in items if isinstance(item, dict))
    elif isinstance(value, list):
        for artifact in value:
            if isinstance(artifact, dict) and _clean(artifact.get("agent")):
                result.setdefault(_clean(artifact.get("agent")).lower(), []).append(artifact)
    return result


def _artifact_revision(artifact):
    artifact = artifact if isinstance(artifact, dict) else {}
    lineage = artifact.get("evidence_lineage") if isinstance(artifact.get("evidence_lineage"), dict) else {}
    packaging = artifact.get("git_packaging") if isinstance(artifact.get("git_packaging"), dict) else {}
    return _clean(lineage.get("source_commit") or artifact.get("source_commit") or artifact.get("tested_revision") or artifact.get("expected_revision") or artifact.get("commit_sha") or packaging.get("commit_sha"))


def _latest_artifact_revision(artifacts):
    for artifact in reversed(list(artifacts.values())):
        revision = _artifact_revision(artifact)
        if revision:
            return revision
    return ""


def _artifact_id(artifact):
    artifact = artifact if isinstance(artifact, dict) else {}
    lineage = artifact.get("evidence_lineage") if isinstance(artifact.get("evidence_lineage"), dict) else {}
    return _clean(lineage.get("artifact_id") or artifact.get("artifact_id"))


def _artifact_sort_key(artifact):
    lineage = artifact.get("evidence_lineage") if isinstance(artifact.get("evidence_lineage"), dict) else {}
    return (_clean(lineage.get("created_at") or artifact.get("completed_at")), int(lineage.get("attempt") or artifact.get("attempt") or 0))


def _basic_judgement(artifact):
    quality_gate = artifact.get("quality_gate") if isinstance(artifact.get("quality_gate"), dict) else {}
    if quality_gate.get("passed") is False:
        return {"passed": False, "reason": _clean(quality_gate.get("reason")) or "quality_gate_failed"}
    values = [artifact.get("pass_fail_status"), artifact.get("status"), artifact.get("recommended_owner_decision")]
    values.extend([artifact.get("test_status"), artifact.get("red_team_status"), artifact.get("visual_acceptance_decision")])
    values = {_clean(value).lower() for value in values if _clean(value)}
    if values.intersection(FAIL_RESULTS):
        return {"passed": False, "reason": "artifact_records_non_passing_decision"}
    return {"passed": True, "reason": "artifact_has_no_non_passing_decision"}


def _recommended_action(blockers, refresh):
    if blockers:
        return {"action": "send_back", "target_agent": blockers[0]["agent"], "reason": blockers[0]["reason"]}
    if refresh:
        return {"action": "targeted_recheck", "target_agent": refresh[0]["agent"], "reason": refresh[0]["reason"]}
    return {"action": "owner_review", "target_agent": "owner", "reason": "current_candidate_evidence_passed"}


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, default=str, separators=(",", ":")).encode("utf-8")).hexdigest()[:24]


def _list(value):
    if isinstance(value, list):
        return value
    if value in (None, ""):
        return []
    return [value]


def _clean(value):
    return " ".join(str(value or "").strip().split())


def _now():
    return datetime.now(timezone.utc).isoformat()
