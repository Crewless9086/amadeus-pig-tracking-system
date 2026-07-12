import hashlib
from datetime import datetime, timezone

from modules.charlie import mission_store, vault_store
from modules.charlie.mission_memory import replay_packet
from modules.charlie.mission_quality import classify_known_failures, score_mission_quality


PROPOSAL_ARTIFACT_TYPE = "charlie_improvement_proposal"
OBSERVATION_ARTIFACT_TYPE = "charlie_improvement_observation"
PROPOSAL_LABEL = "charlie_self_improvement"
ALLOWED_PROPOSAL_DECISIONS = {"approve", "reject", "send_to_mission"}
TERMINAL_MISSION_STATUSES = {"pr_ready", "done", "merged", "deployed", "blocked", "rejected"}
VALIDATION_SAMPLE_MINIMUM = 3

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
    "vault_retrieval": {
        "keywords": ["vault", "vault_sources_used", "source coverage", "retrieval", "brain"],
        "recommendation": "Improve Vault retrieval, required source coverage, and source selection evidence for this mission type.",
    },
    "brain_guard": {
        "keywords": ["brain guard", "brain_guard", "vault discipline", "update discipline", "no_vault_update_required"],
        "recommendation": "Tighten Brain Guard checks so ignored or stale Vault doctrine blocks earlier with clearer repair instructions.",
    },
    "owner_preferences": {
        "keywords": ["owner preference", "buttons", "messy", "overflow", "missing button", "not what i want"],
        "recommendation": "Convert owner feedback into enforced prompt rules, UI standards, and mission acceptance checks.",
    },
    "branch_release": {
        "keywords": ["branch_repair_required", "merge conflict", "conflicting", "stale branch", "wrong revision"],
        "recommendation": "Improve exact-revision materialization and automatic branch repair before review stages consume evidence.",
    },
    "environment": {
        "keywords": ["environment_retry_required", "browser unavailable", "tool unavailable", "timeout", "permissionerror"],
        "recommendation": "Strengthen runner capability fallbacks and retry only the smallest environment-dependent stage.",
    },
    "agent_performance": {
        "keywords": ["contract retry", "repeated backflow", "confidence", "wrong responsible stage", "agent_stage_recovery_queued"],
        "recommendation": "Review agent instructions, evidence contracts, routing accuracy, and repeated-stage performance using measured mission outcomes.",
    },
    "cost_model": {
        "keywords": ["token", "cost", "budget", "expensive", "model routing", "provider fallback"],
        "recommendation": "Right-size model routing and context budgets while preserving deterministic verification and owner gates.",
    },
}


def analyze_improvement_opportunities(missions):
    missions = [mission for mission in missions if isinstance(mission, dict)]
    buckets = {area: _empty_bucket(area) for area in TARGET_AREAS}
    for mission in missions:
        evidence_texts = _mission_improvement_evidence_texts(mission)
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


def run_operational_analyst(mission_id="", trigger="mission_terminal", limit=50, database_url=None, connect_factory=None):
    before, _before_status = list_improvement_proposals(
        limit=limit,
        database_url=database_url,
        connect_factory=connect_factory,
    )
    existing_ids = {proposal.get("proposal_id") for proposal in before.get("proposals", [])} if isinstance(before, dict) else set()
    observation = {}
    if mission_id:
        observation, observation_status = record_mission_observation(
            mission_id,
            trigger=trigger,
            database_url=database_url,
            connect_factory=connect_factory,
        )
        if observation_status >= 400:
            return observation, observation_status
    generated, generated_status = generate_and_store_proposals(
        limit=limit,
        database_url=database_url,
        connect_factory=connect_factory,
    )
    if generated_status >= 400:
        return generated, generated_status
    new_proposals = [proposal for proposal in generated.get("proposals", []) if proposal.get("proposal_id") not in existing_ids]
    lifecycle, lifecycle_status = refresh_proposal_lifecycle(
        limit=limit,
        database_url=database_url,
        connect_factory=connect_factory,
    )
    if lifecycle_status >= 400:
        return lifecycle, lifecycle_status
    scorecard, scorecard_status = analyst_scorecard(
        limit=limit,
        database_url=database_url,
        connect_factory=connect_factory,
    )
    return {
        "success": generated_status < 400 and lifecycle_status < 400 and scorecard_status < 400,
        "status": "analyst_cycle_complete",
        "trigger": trigger,
        "mission_id": mission_id,
        "observation": observation,
        "generated": generated,
        "new_proposals": new_proposals,
        "lifecycle": lifecycle,
        "scorecard": scorecard.get("scorecard", {}),
        "execution_boundary": _execution_boundary(),
    }, max(generated_status, lifecycle_status, scorecard_status)


def record_mission_observation(mission_id, trigger="mission_terminal", database_url=None, connect_factory=None):
    loaded, status_code = mission_store.get_mission(
        mission_id,
        database_url=database_url,
        connect_factory=connect_factory,
    )
    if status_code >= 400:
        return loaded, status_code
    mission = loaded.get("mission") or {}
    status = _clean(mission.get("status"), 40)
    if status not in TERMINAL_MISSION_STATUSES:
        return {
            "success": True,
            "status": "observation_skipped_non_terminal",
            "mission_id": mission_id,
            "mission_status": status,
        }, 200
    packet = (mission.get("metadata") or {}).get("review_packet") or {}
    disposition = packet.get("block_disposition") if isinstance(packet.get("block_disposition"), dict) else {}
    fingerprint_seed = "|".join([
        mission_id,
        status,
        str(packet.get("review_status") or ""),
        str(disposition.get("block_class") or ""),
        str((packet.get("github_reconciliation") or {}).get("head_sha") or packet.get("tested_revision") or ""),
    ])
    fingerprint = hashlib.sha256(fingerprint_seed.encode("utf-8")).hexdigest()[:20]
    ledger = packet.get("agent_execution") if isinstance(packet.get("agent_execution"), dict) else {}
    stages = ledger.get("stages") if isinstance(ledger.get("stages"), list) else []
    observation = {
        "version": "charlie_analyst_observation_v1",
        "observation_id": f"CHARLIE-OBS-{fingerprint.upper()}",
        "fingerprint": fingerprint,
        "mission_id": mission_id,
        "mission_status": status,
        "trigger": _clean(trigger, 80),
        "title": _clean(mission.get("title") or mission.get("raw_text"), 200),
        "mission_type": _clean(mission.get("mission_type"), 80),
        "review_status": _clean(packet.get("review_status"), 80),
        "block_class": _clean(disposition.get("block_class"), 80),
        "owner_required": bool(disposition.get("owner_required")),
        "responsible_stage": _clean(disposition.get("responsible_stage"), 80),
        "backflow_count": len(packet.get("backflow_events") or []),
        "contract_retry_count": len(ledger.get("contract_retries") or []),
        "stage_count": len(stages),
        "test_evidence_count": len(packet.get("test_evidence") or []),
        "owner_decision": _clean(mission.get("owner_decision"), 500),
        "evidence": _mission_evidence_texts(mission)[:20],
        "recorded_at": datetime.now(timezone.utc).isoformat(),
        "applies_automatically": False,
    }
    written, write_status = vault_store.write_artifact(
        mission_id,
        OBSERVATION_ARTIFACT_TYPE,
        observation,
        title=observation["observation_id"],
        summary=f"ANALYST observed {status} outcome for {mission_id}.",
        agent="charlie_improvement_analyst",
        database_url=database_url,
        connect_factory=connect_factory,
    )
    return {
        "success": write_status < 400 and written.get("success", False),
        "status": "observation_recorded" if write_status < 400 else written.get("status", "observation_write_failed"),
        "observation": observation,
    }, write_status


def analyze_mission_replay(mission):
    mission = mission if isinstance(mission, dict) else {}
    replay = replay_packet(mission)
    review_packet = replay.get("review_packet") if isinstance(replay.get("review_packet"), dict) else {}
    debug_focus = replay.get("debug_focus") if isinstance(replay.get("debug_focus"), dict) else {}
    events = replay.get("timeline") if isinstance(replay.get("timeline"), list) else []
    mission_quality = review_packet.get("mission_quality") if isinstance(review_packet.get("mission_quality"), dict) else score_mission_quality(mission, review_packet, review_packet.get("agent_execution", {}))
    known_failures = classify_known_failures(str(review_packet), str(debug_focus), str(events))
    findings = []
    proposals = []
    if debug_focus.get("blocked_reason"):
        findings.append(f"Mission blocked at {debug_focus.get('blocked_agent') or 'unknown agent'}: {debug_focus.get('blocked_reason')}")
        proposals.append({
            "target_area": "gates",
            "problem_detected": "Blocked mission needs clearer recovery path.",
            "recommendation": "Use mission replay, recovery notes, and final artifact contract to rerun from the smallest responsible stage.",
            "applies_automatically": False,
        })
    if review_packet and not review_packet.get("test_evidence"):
        findings.append("Review packet is missing test evidence.")
        proposals.append({
            "target_area": "tests",
            "problem_detected": "Review packet missing test evidence.",
            "recommendation": "Block owner review until tester/reviewer records focused verification evidence.",
            "applies_automatically": False,
        })
    if len([event for event in events if event.get("type") == "backflow"]) >= 2:
        findings.append("Mission had repeated backflow events.")
        proposals.append({
            "target_area": "prompts",
            "problem_detected": "Repeated backflow suggests weak upstream acceptance criteria or incomplete implementation brief.",
            "recommendation": "Strengthen planner/architect artifacts and require council synthesis before another write attempt.",
            "applies_automatically": False,
        })
    for failure in known_failures:
        findings.append(f"Known failure pattern detected: {failure.get('code')} - {failure.get('summary')}")
        proposals.append({
            "target_area": _target_area_for_failure(failure.get("code", "")),
            "problem_detected": f"Known CHARLIE failure pattern: {failure.get('code', '')}",
            "recommendation": " ".join(failure.get("recovery_steps", [])) or failure.get("summary", ""),
            "applies_automatically": False,
            "known_failure_code": failure.get("code", ""),
            "severity": failure.get("severity", ""),
        })
    if not findings:
        findings.append("No critical replay weakness detected from current stored evidence.")
    return {
        "success": True,
        "status": "ok",
        "mode": "advisory_replay_analysis_only",
        "mission_id": replay.get("mission_id", ""),
        "findings": findings,
        "proposals": proposals,
        "mission_quality": mission_quality,
        "known_failures": known_failures,
        "replay": replay,
        "execution_boundary": _execution_boundary(),
    }, 200


def generate_and_store_proposals(limit=50, max_proposals=5, database_url=None, connect_factory=None):
    loaded, status_code = mission_store.list_missions(
        limit=limit,
        database_url=database_url,
        connect_factory=connect_factory,
    )
    if status_code >= 400:
        return loaded, status_code
    proposals = analyze_improvement_opportunities(loaded.get("missions", []))[:max(1, min(int(max_proposals or 5), 10))]
    existing_by_id = _existing_proposals_by_id(database_url=database_url, connect_factory=connect_factory)
    current_ids = {proposal["proposal_id"] for proposal in proposals}
    superseded = []
    for proposal_id, existing in existing_by_id.items():
        if proposal_id in current_ids or existing.get("status") not in {"pending", "pending_owner_review"}:
            continue
        artifact_id = existing.get("artifact_id")
        if not artifact_id:
            continue
        stale = dict(existing)
        stale["status"] = "superseded"
        stale["superseded_reason"] = "Current structured mission evidence no longer meets the recurrence threshold."
        stale["lifecycle_updated_at"] = datetime.now(timezone.utc).isoformat()
        saved, saved_status = vault_store.update_artifact_content(
            artifact_id,
            stale,
            summary=stale.get("recommendation", ""),
            database_url=database_url,
            connect_factory=connect_factory,
        )
        superseded.append({"proposal_id": proposal_id, "success": saved_status < 400 and saved.get("success", False)})
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
    failed_writes = [write for write in writes if not write.get("success") or int(write.get("status_code") or 500) >= 400]
    if failed_writes:
        return {
            "success": False,
            "configured": True,
            "status": "proposal_write_failed",
            "proposal_count": len(proposals),
            "failed_write_count": len(failed_writes),
            "proposals": proposals,
            "writes": writes,
            "execution_boundary": _execution_boundary(),
        }, max(int(write.get("status_code") or 500) for write in failed_writes)
    return {
        "success": True,
        "configured": True,
        "status": "ok",
        "proposal_count": len(proposals),
        "proposals": proposals,
        "writes": writes,
        "superseded": superseded,
        "execution_boundary": _execution_boundary(),
    }, 200


def create_owner_gated_improvement_missions(limit=50, max_create=3, database_url=None, connect_factory=None):
    generated, status_code = generate_and_store_proposals(
        limit=limit,
        database_url=database_url,
        connect_factory=connect_factory,
    )
    if status_code >= 400:
        return generated, status_code
    proposals = generated.get("proposals") if isinstance(generated.get("proposals"), list) else []
    candidates = [
        proposal for proposal in proposals
        if proposal.get("status") == "pending"
        and int(proposal.get("weakness_score") or 0) >= 70
        and proposal.get("applies_automatically") is False
    ][:max(1, min(int(max_create or 3), 10))]
    created = []
    for proposal in candidates:
        mission_result, mission_status = _create_improvement_mission(
            proposal,
            "Created automatically by Analyst loop as owner-gated improvement mission. Owner approval still required before build.",
            database_url,
            connect_factory,
        )
        created.append({
            "proposal_id": proposal.get("proposal_id", ""),
            "target_area": proposal.get("target_area", ""),
            "status_code": mission_status,
            "created": bool(mission_result.get("stored")),
            "mission_id": mission_result.get("mission_id", ""),
            "mission_status": mission_result.get("status", ""),
        })
        if mission_status < 400 and mission_result.get("mission_id") and proposal.get("artifact_id"):
            updated = dict(proposal)
            updated["status"] = "mission_created"
            updated["sent_to_mission_id"] = mission_result["mission_id"]
            updated["mission_creation_status"] = mission_result.get("status", "mission_recorded")
            updated["lifecycle_updated_at"] = datetime.now(timezone.utc).isoformat()
            vault_store.update_artifact_content(
                proposal["artifact_id"],
                updated,
                summary=updated.get("recommendation", ""),
                database_url=database_url,
                connect_factory=connect_factory,
            )
    return {
        "success": True,
        "configured": True,
        "status": "ok",
        "created_count": len([item for item in created if item.get("created")]),
        "created": created,
        "execution_boundary": "Analyst may create owner-gated improvement missions only; it does not approve, build, merge, deploy, or modify production behavior.",
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
        "baseline",
        "validation",
        "problem_fingerprint",
        "lifecycle_updated_at",
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


def refresh_proposal_lifecycle(limit=50, database_url=None, connect_factory=None):
    proposals_result, proposal_status = list_improvement_proposals(
        limit=limit,
        database_url=database_url,
        connect_factory=connect_factory,
    )
    if proposal_status >= 400:
        return proposals_result, proposal_status
    missions_result, mission_status = mission_store.list_missions(
        limit=limit,
        database_url=database_url,
        connect_factory=connect_factory,
    )
    if mission_status >= 400:
        return missions_result, mission_status
    missions = missions_result.get("missions", [])
    missions_by_id = {str(mission.get("mission_id") or ""): mission for mission in missions}
    updates = []
    for proposal in proposals_result.get("proposals", []):
        artifact_id = proposal.get("artifact_id")
        if not artifact_id:
            continue
        mission_id = str(proposal.get("sent_to_mission_id") or "").strip()
        improvement_mission = missions_by_id.get(mission_id) if mission_id else None
        old_status = proposal.get("status") or "pending_owner_review"
        new_status = old_status
        validation = proposal.get("validation") if isinstance(proposal.get("validation"), dict) else {}
        if improvement_mission:
            current = str(improvement_mission.get("status") or "").strip()
            if current in {"new", "approved", "in_progress", "blocked", "pr_ready", "release_approved", "release_in_progress"}:
                new_status = "implementation_in_progress"
            elif current in {"done", "merged", "deployed"}:
                new_status = "deployed_pending_validation"
                validation = _validation_assessment(proposal, missions, improvement_mission)
                if validation.get("sample_ready"):
                    new_status = "validated_effective" if validation.get("effective") else "validated_ineffective"
        if new_status == old_status and validation == proposal.get("validation", {}):
            continue
        updated = dict(proposal)
        updated["status"] = new_status
        updated["validation"] = validation
        updated["lifecycle_updated_at"] = datetime.now(timezone.utc).isoformat()
        saved, saved_status = vault_store.update_artifact_content(
            artifact_id,
            updated,
            summary=updated.get("recommendation", ""),
            database_url=database_url,
            connect_factory=connect_factory,
        )
        updates.append({
            "proposal_id": proposal.get("proposal_id"),
            "artifact_id": artifact_id,
            "from": old_status,
            "to": new_status,
            "success": saved_status < 400 and saved.get("success", False),
        })
    return {
        "success": all(item.get("success") for item in updates),
        "status": "proposal_lifecycle_refreshed",
        "updated_count": len(updates),
        "updates": updates,
    }, 200


def analyst_scorecard(limit=50, database_url=None, connect_factory=None):
    proposals_result, proposal_status = list_improvement_proposals(
        limit=limit,
        database_url=database_url,
        connect_factory=connect_factory,
    )
    if proposal_status >= 400:
        return proposals_result, proposal_status
    observations_result, observation_status = vault_store.list_artifacts(
        artifact_type=OBSERVATION_ARTIFACT_TYPE,
        limit=limit,
        database_url=database_url,
        connect_factory=connect_factory,
    )
    if observation_status >= 400:
        return observations_result, observation_status
    proposals = proposals_result.get("proposals", [])
    observations = observations_result.get("artifacts", [])
    accepted = [proposal for proposal in proposals if proposal.get("status") not in {"pending", "pending_owner_review", "rejected"}]
    validated = [proposal for proposal in proposals if str(proposal.get("status") or "").startswith("validated_")]
    effective = [proposal for proposal in validated if proposal.get("status") == "validated_effective"]
    pending = [proposal for proposal in proposals if proposal.get("status") in {"pending", "pending_owner_review", "approved"}]
    return {
        "success": True,
        "status": "analyst_scorecard_ready",
        "scorecard": {
            "observations": len(observations),
            "proposals_total": len(proposals),
            "pending_proposals": len(pending),
            "accepted_proposals": len(accepted),
            "rejected_proposals": len([proposal for proposal in proposals if proposal.get("status") == "rejected"]),
            "improvement_missions": len([proposal for proposal in proposals if proposal.get("sent_to_mission_id")]),
            "validated_improvements": len(validated),
            "effective_improvements": len(effective),
            "proposal_acceptance_rate": 0.0 if not proposals else len(accepted) / len(proposals),
            "validated_effectiveness_rate": 0.0 if not validated else len(effective) / len(validated),
            "last_analysis_at": max(
                [str((artifact.get("content") or {}).get("recorded_at") or artifact.get("created_at") or "") for artifact in observations] or [""]
            ),
            "stage": "proposal_ready" if pending else ("validation_running" if any(proposal.get("status") == "deployed_pending_validation" for proposal in proposals) else "observing"),
        },
        "execution_boundary": _execution_boundary(),
    }, 200


def _validation_assessment(proposal, missions, improvement_mission):
    source_ids = set(proposal.get("source_mission_ids") or [])
    target_area = proposal.get("target_area") or ""
    post_missions = [
        mission for mission in missions
        if mission.get("mission_id") not in source_ids
        and mission.get("mission_id") != improvement_mission.get("mission_id")
        and mission.get("status") in TERMINAL_MISSION_STATUSES
    ]
    affected = [mission for mission in post_missions if _mission_matches_area(mission, target_area)]
    baseline_sample = max(len(source_ids), 1)
    baseline_rate = min(1.0, int(proposal.get("recurrence_count") or len(source_ids)) / baseline_sample)
    post_rate = 0.0 if not post_missions else len(affected) / len(post_missions)
    sample_ready = len(post_missions) >= VALIDATION_SAMPLE_MINIMUM
    effective = sample_ready and post_rate <= baseline_rate * 0.75
    return {
        "version": "charlie_analyst_validation_v1",
        "sample_ready": sample_ready,
        "minimum_sample": VALIDATION_SAMPLE_MINIMUM,
        "post_mission_count": len(post_missions),
        "post_recurrence_count": len(affected),
        "baseline_rate": round(baseline_rate, 4),
        "post_rate": round(post_rate, 4),
        "effective": effective,
        "measured_at": datetime.now(timezone.utc).isoformat(),
    }


def _mission_matches_area(mission, area):
    config = TARGET_AREAS.get(area) or {}
    combined = " ".join(_mission_improvement_evidence_texts(mission)).lower()
    return any(keyword in combined for keyword in config.get("keywords", []))


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
        "approve": "mission_created",
        "reject": "rejected",
        "send_to_mission": "mission_created",
    }[decision]
    proposal["last_owner_decision"] = decision_record
    created_mission = None
    if decision in {"approve", "send_to_mission"}:
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
    evidence_signature = "|".join(sorted(_clean(item.get("evidence"), 180).lower() for item in bucket["evidence_refs"] if item.get("evidence")))
    problem_fingerprint = hashlib.sha256(f"{area}|{evidence_signature}".encode("utf-8")).hexdigest()[:16]
    source_count = len(bucket["source_mission_ids"])
    return {
        "proposal_id": proposal_id,
        "label": PROPOSAL_LABEL,
        "problem_detected": f"Repeated {area.replace('_', ' ')} weakness across CHARLIE missions.",
        "evidence_refs": bucket["evidence_refs"][:8],
        "recurrence_count": len(bucket["source_mission_ids"]),
        "problem_fingerprint": problem_fingerprint,
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
        "baseline": {
            "source_mission_count": source_count,
            "recurrence_count": source_count,
            "recurrence_rate": 1.0 if source_count else 0.0,
            "captured_at": datetime.now(timezone.utc).isoformat(),
        },
        "validation": {
            "sample_ready": False,
            "minimum_sample": VALIDATION_SAMPLE_MINIMUM,
            "post_mission_count": 0,
        },
    }


def _target_area_for_failure(code):
    code = str(code or "").strip().lower()
    if code in {"pytest_missing", "windows_temp_lock"}:
        return "tests"
    if code in {"stale_review_packet", "review_media_missing"}:
        return "gates"
    if code in {"branch_mismatch", "powershell_redirect_conflict", "powershell_quoting"}:
        return "runner_behavior"
    return "templates"


def _mission_evidence_texts(mission):
    metadata = mission.get("metadata") if isinstance(mission.get("metadata"), dict) else {}
    vault = mission.get("vault") if isinstance(mission.get("vault"), dict) else {}
    review_packet = metadata.get("review_packet") if isinstance(metadata.get("review_packet"), dict) else {}
    disposition = review_packet.get("block_disposition") if isinstance(review_packet.get("block_disposition"), dict) else {}
    values = [
        mission.get("title", ""),
        mission.get("raw_text", ""),
        mission.get("owner_decision", ""),
        vault.get("problem_statement", ""),
        vault.get("desired_outcome", ""),
        review_packet.get("summary", ""),
        review_packet.get("blocked_reason", ""),
        review_packet.get("recommended_next_action", ""),
        disposition.get("block_class", ""),
        disposition.get("responsible_stage", ""),
        disposition.get("scope_relation", ""),
    ]
    for key in ["findings", "errors", "bugs", "test_evidence", "qa_evidence", "backflow_events", "unresolved_blockers"]:
        value = review_packet.get(key)
        if isinstance(value, list):
            values.extend(str(item) for item in value)
    for item in mission.get("agent_workflow", []) if isinstance(mission.get("agent_workflow"), list) else []:
        if isinstance(item, dict):
            values.append(item.get("findings", ""))
    return [_clean(value, 800) for value in values if _clean(value, 800)]


def _mission_improvement_evidence_texts(mission):
    metadata = mission.get("metadata") if isinstance(mission.get("metadata"), dict) else {}
    review_packet = metadata.get("review_packet") if isinstance(metadata.get("review_packet"), dict) else {}
    disposition = review_packet.get("block_disposition") if isinstance(review_packet.get("block_disposition"), dict) else {}
    values = [
        mission.get("owner_decision", ""),
        review_packet.get("blocked_reason", ""),
        disposition.get("block_class", ""),
        disposition.get("responsible_stage", ""),
    ]
    for key in ("errors", "bugs", "unresolved_blockers", "backflow_events"):
        value = review_packet.get(key)
        if isinstance(value, list):
            values.extend(str(item) for item in value)
        elif value:
            values.append(value)
    for item in mission.get("agent_workflow", []) if isinstance(mission.get("agent_workflow"), list) else []:
        if isinstance(item, dict) and str(item.get("status") or "").lower() == "blocked":
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
