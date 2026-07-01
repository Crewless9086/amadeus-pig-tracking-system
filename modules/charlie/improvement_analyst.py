from datetime import datetime, timezone

from modules.charlie import mission_store, vault_store


PROPOSAL_ARTIFACT_TYPE = "charlie_improvement_proposal"
PROPOSAL_LABEL = "charlie_self_improvement"
ALLOWED_PROPOSAL_DECISIONS = {"approve", "reject", "send_to_mission"}

TARGET_AREAS = {
    "tests": {
        "keywords": ["test", "tests", "failed", "failure", "regression", "qa"],
        "recommendation": "Tighten test gates and require clearer automated evidence before owner review.",
    },
    "gates": {
        "keywords": ["gate", "blocked", "blocker", "hard stop", "quality"],
        "recommendation": "Strengthen quality-gate visibility and block earlier when required evidence is missing.",
    },
    "dashboard_visibility": {
        "keywords": ["dashboard", "visibility", "owner review", "review packet", "panel", "display"],
        "recommendation": "Expose the missing state in the CHARLIE dashboard so the owner can review it without reading raw artifacts.",
    },
    "runner_behavior": {
        "keywords": ["runner", "pickup", "heartbeat", "codex", "handoff", "backflow"],
        "recommendation": "Improve runner handoff reporting and make stuck or repeated backflow states more explicit.",
    },
    "prompts": {
        "keywords": ["prompt", "instruction", "scope", "forbidden", "approval"],
        "recommendation": "Clarify prompt instructions and mission packets so agents consistently respect scope and hard stops.",
    },
    "templates": {
        "keywords": ["template", "artifact", "handoff", "packet", "format"],
        "recommendation": "Update mission templates so repeated missing evidence is captured consistently.",
    },
    "docs": {
        "keywords": ["docs", "documentation", "sop", "protocol", "current_state", "next_steps"],
        "recommendation": "Update CHARLIE docs where repeated operator confusion or stale guidance appears.",
    },
}


def analyze_improvement_opportunities(missions):
    missions = [mission for mission in missions if isinstance(mission, dict)]
    buckets = {area: _empty_bucket(area) for area in TARGET_AREAS}
    for mission in missions:
        evidence_texts = _mission_evidence_texts(mission)
        combined = " ".join(evidence_texts).lower()
        if not combined:
            continue
        for area, config in TARGET_AREAS.items():
            if mission.get("status") == "blocked" and area == "gates":
                _add_evidence(buckets[area], mission, "Mission entered blocked status.")
            if any(keyword in combined for keyword in config["keywords"]):
                _add_evidence(buckets[area], mission, _first_relevant_text(evidence_texts, config["keywords"]))

    proposals = []
    for area, bucket in buckets.items():
        recurrence_count = len(bucket["source_mission_ids"])
        if recurrence_count < 2:
            continue
        score = _weakness_score(area, recurrence_count, bucket["evidence_refs"])
        proposals.append(_proposal(area, bucket, score))
    proposals.sort(key=lambda item: (-item["weakness_score"], item["target_area"]))
    return proposals


def generate_and_store_proposals(limit=50, database_url=None, connect_factory=None):
    loaded, status_code = mission_store.list_missions(
        limit=limit,
        database_url=database_url,
        connect_factory=connect_factory,
    )
    if status_code >= 400:
        return loaded, status_code
    proposals = analyze_improvement_opportunities(loaded.get("missions", []))
    existing_by_id = _existing_proposals_by_id(database_url=database_url, connect_factory=connect_factory)
    writes = []
    for proposal in proposals:
        proposal = _merge_existing_proposal_decision(proposal, existing_by_id.get(proposal["proposal_id"]))
        proposal["record_mission_id"] = _proposal_record_mission_id(proposal)
        result, write_status = vault_store.write_artifact(
            proposal["record_mission_id"],
            PROPOSAL_ARTIFACT_TYPE,
            proposal,
            title=proposal["problem_detected"],
            summary=proposal["recommendation"],
            project_id="",
            agent="charlie_improvement_analyst",
            database_url=database_url,
            connect_factory=connect_factory,
        )
        writes.append({"proposal_id": proposal["proposal_id"], "status": result.get("status"), "success": result.get("success"), "status_code": write_status})
    return {
        "success": True,
        "configured": True,
        "status": "ok",
        "proposal_count": len(proposals),
        "proposals": proposals,
        "writes": writes,
        "execution_boundary": _execution_boundary(),
    }, 200


def _existing_proposals_by_id(database_url=None, connect_factory=None):
    loaded, status_code = vault_store.list_artifacts(
        artifact_type=PROPOSAL_ARTIFACT_TYPE,
        limit=50,
        database_url=database_url,
        connect_factory=connect_factory,
    )
    if status_code >= 400:
        return {}
    proposals = {}
    for artifact in loaded.get("artifacts", []):
        proposal = _proposal_from_artifact(artifact)
        proposal_id = _clean(proposal.get("proposal_id", ""), 160)
        if proposal_id:
            proposals[proposal_id] = proposal
    return proposals


def _merge_existing_proposal_decision(proposal, existing):
    if not isinstance(existing, dict):
        return proposal
    preserved = dict(proposal)
    existing_status = _clean(existing.get("status", ""), 40)
    if existing_status and existing_status != "pending":
        preserved["status"] = existing_status
    for key in [
        "decision_history",
        "last_owner_decision",
        "mission_creation_status",
        "sent_to_mission_id",
    ]:
        if existing.get(key):
            preserved[key] = existing[key]
    if existing.get("created_at"):
        preserved["created_at"] = existing["created_at"]
    if existing.get("artifact_id"):
        preserved["artifact_id"] = existing["artifact_id"]
    return preserved


def list_improvement_proposals(status="", limit=20, database_url=None, connect_factory=None):
    result, status_code = vault_store.list_artifacts(
        artifact_type=PROPOSAL_ARTIFACT_TYPE,
        limit=limit,
        database_url=database_url,
        connect_factory=connect_factory,
    )
    if status_code >= 400:
        return result, status_code
    clean_status = _clean(status, 40)
    proposals = []
    for artifact in result.get("artifacts", []):
        proposal = _proposal_from_artifact(artifact)
        if clean_status and proposal.get("status") != clean_status:
            continue
        proposals.append(proposal)
    return {
        "success": True,
        "configured": result.get("configured", True),
        "status": "ok",
        "proposals": proposals,
        "execution_boundary": _execution_boundary(),
    }, 200


def record_proposal_decision(proposal_id, decision, comments="", database_url=None, connect_factory=None):
    proposal_id = _clean(proposal_id, 160)
    decision = _clean(decision, 40)
    comments = _clean(comments, 1200)
    if not proposal_id:
        return {"success": False, "status": "proposal_id_required"}, 400
    if decision not in ALLOWED_PROPOSAL_DECISIONS:
        return {"success": False, "status": "invalid_improvement_decision", "allowed_decisions": sorted(ALLOWED_PROPOSAL_DECISIONS)}, 400

    loaded, load_status = vault_store.get_artifact(
        proposal_id,
        database_url=database_url,
        connect_factory=connect_factory,
    )
    if load_status >= 400:
        return loaded, load_status
    artifact = loaded.get("artifact") or {}
    proposal = _proposal_from_artifact(artifact)
    if proposal.get("label") != PROPOSAL_LABEL:
        return {"success": False, "status": "invalid_improvement_label"}, 409

    decision_record = {
        "decision": decision,
        "comments": comments,
        "recorded_at": datetime.now(timezone.utc).isoformat(),
        "applies_automatically": False,
    }
    proposal["decision_history"] = (proposal.get("decision_history") or [])[-19:] + [decision_record]
    proposal["status"] = {
        "approve": "approved",
        "reject": "rejected",
        "send_to_mission": "sent_to_mission",
    }[decision]
    proposal["last_owner_decision"] = decision_record
    created_mission = None
    if decision == "send_to_mission":
        created_mission, mission_status = _create_improvement_mission(proposal, comments, database_url, connect_factory)
        proposal["mission_creation_status"] = created_mission.get("status")
        if created_mission.get("mission_id"):
            proposal["sent_to_mission_id"] = created_mission["mission_id"]
        if mission_status >= 400:
            proposal["status"] = "approved"

    saved, save_status = vault_store.update_artifact_content(
        proposal_id,
        proposal,
        summary=proposal.get("recommendation", ""),
        database_url=database_url,
        connect_factory=connect_factory,
    )
    if save_status >= 400:
        return saved, save_status
    decision_mission_id = _proposal_record_mission_id(proposal)
    vault_store.write_owner_decision(
        decision_mission_id,
        f"improvement_proposal_{decision}",
        comments=comments,
        metadata={"proposal_id": proposal_id, "label": PROPOSAL_LABEL, "applies_automatically": False},
        database_url=database_url,
        connect_factory=connect_factory,
    )
    return {
        "success": True,
        "configured": True,
        "status": "ok",
        "proposal_id": proposal_id,
        "proposal_status": proposal["status"],
        "decision": decision,
        "created_mission": created_mission or {},
        "execution_boundary": _execution_boundary(),
    }, 200


def _create_improvement_mission(proposal, comments, database_url, connect_factory):
    raw_text = "\n".join([
        f"CHARLIE self-improvement proposal: {proposal.get('problem_detected', '')}",
        f"Recommendation: {proposal.get('recommendation', '')}",
        f"Target area: {proposal.get('target_area', '')}",
        f"Owner comments: {comments}" if comments else "",
    ]).strip()
    return mission_store.record_mission(
        {
            "raw_text": raw_text,
            "title": f"CHARLIE Improvement: {proposal.get('target_area', 'workflow')}",
            "urgency": "P2",
            "mission_type": "system improvement",
            "approval_level": "LEVEL 3",
            "desired_outcome": "Owner-reviewed CHARLIE CORE improvement is implemented through the normal mission workflow.",
            "acceptance_criteria": [
                "Improvement is built only through normal CHARLIE mission stages.",
                "No proposal content applies itself automatically.",
            ],
            "forbidden_actions": [
                "Do not self-edit prompts, runtime rules, migrations, deployments, or production data directly from this proposal.",
            ],
            "metadata": {
                "created_from": "charlie_improvement_proposal",
                "source_proposal_id": proposal.get("proposal_id", ""),
                "proposal_label": PROPOSAL_LABEL,
            },
        },
        source_context={"source": "charlie_improvement_analyst"},
        database_url=database_url,
        connect_factory=connect_factory,
    )


def _proposal(area, bucket, score):
    config = TARGET_AREAS[area]
    proposal_id = "CHARLIE-IMPROVEMENT-" + area.upper().replace("_", "-")
    return {
        "proposal_id": proposal_id,
        "label": PROPOSAL_LABEL,
        "problem_detected": f"Repeated {area.replace('_', ' ')} weakness across CHARLIE missions.",
        "evidence_refs": bucket["evidence_refs"][:8],
        "recurrence_count": len(bucket["source_mission_ids"]),
        "weakness_score": score,
        "recommendation": config["recommendation"],
        "target_area": area,
        "impact": "high" if score >= 80 else "medium",
        "effort": "medium",
        "confidence": "medium" if len(bucket["source_mission_ids"]) < 4 else "high",
        "status": "pending",
        "source_mission_ids": sorted(bucket["source_mission_ids"]),
        "record_mission_id": sorted(bucket["source_mission_ids"])[0],
        "created_by_agent": "charlie_improvement_analyst",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "applies_automatically": False,
    }


def _mission_evidence_texts(mission):
    metadata = mission.get("metadata") if isinstance(mission.get("metadata"), dict) else {}
    vault = mission.get("vault") if isinstance(mission.get("vault"), dict) else {}
    review_packet = metadata.get("review_packet") if isinstance(metadata.get("review_packet"), dict) else {}
    values = [
        mission.get("title", ""),
        mission.get("raw_text", ""),
        mission.get("owner_decision", ""),
        vault.get("problem_statement", ""),
        vault.get("desired_outcome", ""),
        review_packet.get("summary", ""),
        review_packet.get("blocked_reason", ""),
        review_packet.get("recommended_next_action", ""),
    ]
    for key in ["findings", "errors", "bugs", "test_evidence", "qa_evidence", "backflow_events", "unresolved_blockers"]:
        value = review_packet.get(key)
        if isinstance(value, list):
            values.extend(str(item) for item in value)
    for item in mission.get("agent_workflow", []) if isinstance(mission.get("agent_workflow"), list) else []:
        if isinstance(item, dict):
            values.append(item.get("findings", ""))
    return [_clean(value, 800) for value in values if _clean(value, 800)]


def _empty_bucket(area):
    return {"area": area, "source_mission_ids": set(), "evidence_refs": []}


def _add_evidence(bucket, mission, text):
    mission_id = _clean(mission.get("mission_id", ""), 120)
    if not mission_id:
        return
    bucket["source_mission_ids"].add(mission_id)
    bucket["evidence_refs"].append({
        "mission_id": mission_id,
        "status": _clean(mission.get("status", ""), 40),
        "title": _clean(mission.get("title") or mission.get("raw_text", ""), 160),
        "evidence": _clean(text, 500),
    })


def _first_relevant_text(texts, keywords):
    for text in texts:
        lowered = text.lower()
        if any(keyword in lowered for keyword in keywords):
            return text
    return texts[0] if texts else ""


def _weakness_score(area, recurrence_count, evidence_refs):
    score = 45 + min(recurrence_count, 6) * 8
    if area in {"gates", "tests", "runner_behavior"}:
        score += 8
    if any(ref.get("status") == "blocked" for ref in evidence_refs):
        score += 12
    return min(score, 100)


def _proposal_from_artifact(artifact):
    content = artifact.get("content") if isinstance(artifact.get("content"), dict) else {}
    proposal = dict(content)
    proposal.setdefault("proposal_id", artifact.get("artifact_id", ""))
    proposal.setdefault("artifact_id", artifact.get("artifact_id", ""))
    proposal.setdefault("status", "pending")
    proposal.setdefault("label", PROPOSAL_LABEL)
    proposal.setdefault("created_by_agent", artifact.get("created_by_agent", ""))
    proposal.setdefault("created_at", artifact.get("created_at", ""))
    proposal.setdefault("record_mission_id", artifact.get("mission_id", ""))
    proposal["artifact_id"] = artifact.get("artifact_id", proposal.get("artifact_id", ""))
    proposal["mission_id"] = artifact.get("mission_id", proposal.get("mission_id", ""))
    return proposal


def _proposal_record_mission_id(proposal):
    mission_id = _clean(proposal.get("record_mission_id") or proposal.get("mission_id"), 120)
    if mission_id:
        return mission_id
    source_ids = proposal.get("source_mission_ids") if isinstance(proposal.get("source_mission_ids"), list) else []
    cleaned = sorted(_clean(source_id, 120) for source_id in source_ids if _clean(source_id, 120))
    return cleaned[0] if cleaned else ""


def _execution_boundary():
    return "Improvement proposals are advisory records only; owner decisions may approve, reject, or create a normal mission, but proposals never self-edit, merge, deploy, migrate, or change runtime rules."


def _clean(value, max_len):
    return " ".join(str(value or "").strip().split())[:max_len]
