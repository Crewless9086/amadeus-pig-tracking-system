from datetime import datetime, timezone


MISSION_MEMORY_VERSION = "charlie_mission_memory_v1"
FINAL_ARTIFACT_CONTRACT_VERSION = "charlie_final_artifact_contract_v2"
PARTIAL_RECOVERY_VERSION = "charlie_partial_recovery_agent_v1"
PARALLEL_PLANNING_VERSION = "charlie_parallel_agent_planning_v1"

MAX_EVENTS = 80
MAX_ATTEMPTS = 40
MAX_AGENT_NOTES = 40
MAX_HANDOFFS = 40
MAX_RECOVERY_NOTES = 30
MAX_TEXT = 1200


def mission_memory_from_metadata(metadata):
    metadata = metadata if isinstance(metadata, dict) else {}
    memory = metadata.get("mission_memory") if isinstance(metadata.get("mission_memory"), dict) else {}
    if not memory:
        memory = {}
    memory = {
        "version": memory.get("version") or MISSION_MEMORY_VERSION,
        "status": memory.get("status") or "active",
        "events": _list(memory.get("events"))[-MAX_EVENTS:],
        "attempts": _list(memory.get("attempts"))[-MAX_ATTEMPTS:],
        "agent_notes": _list(memory.get("agent_notes"))[-MAX_AGENT_NOTES:],
        "handoffs": _list(memory.get("handoffs"))[-MAX_HANDOFFS:],
        "recovery_notes": _list(memory.get("recovery_notes"))[-MAX_RECOVERY_NOTES:],
        "latest_by_agent": memory.get("latest_by_agent") if isinstance(memory.get("latest_by_agent"), dict) else {},
        "open_questions": _list(memory.get("open_questions"))[-30:],
        "updated_at": memory.get("updated_at") or "",
    }
    return memory


def build_memory_event(agent, event_type, summary="", attempt=1, artifact=None, quality_gate=None, recovery=None, metadata=None):
    artifact = artifact if isinstance(artifact, dict) else {}
    quality_gate = quality_gate if isinstance(quality_gate, dict) else {}
    recovery = recovery if isinstance(recovery, dict) else {}
    metadata = metadata if isinstance(metadata, dict) else {}
    event = {
        "agent": _clean(agent, 80),
        "type": _clean(event_type, 80),
        "attempt": _int(attempt, 1),
        "summary": _clean(summary or artifact.get("summary") or event_type, MAX_TEXT),
        "recorded_at": _utc_now(),
        "confidence": _clean(artifact.get("confidence"), 40),
        "confidence_reason": _clean(artifact.get("confidence_reason"), 600),
        "quality_gate": quality_gate,
        "files_inspected": _clean_list(artifact.get("files_inspected"), 18, 220),
        "changed_files": _clean_list(artifact.get("changed_files"), 18, 220),
        "commands_run": _clean_list(artifact.get("commands_run"), 12, 260),
        "tests_run": _clean_list(artifact.get("tests_run") or artifact.get("test_evidence"), 12, 260),
        "risks": _clean_list(artifact.get("risk_notes") or artifact.get("risks") or artifact.get("qa_findings"), 12, 260),
        "next_action": _clean(artifact.get("next_action") or artifact.get("recommended_owner_decision"), 500),
        "artifact_path": _clean(artifact.get("artifact_path"), 260),
        "recovery": recovery,
        "metadata": metadata,
    }
    return {key: value for key, value in event.items() if value not in ("", [], {}, None)}


def append_memory_event(metadata, event):
    metadata = dict(metadata if isinstance(metadata, dict) else {})
    event = event if isinstance(event, dict) else {}
    memory = mission_memory_from_metadata(metadata)
    if not event.get("recorded_at"):
        event["recorded_at"] = _utc_now()
    memory["events"] = [*memory["events"], event][-MAX_EVENTS:]
    agent = _clean(event.get("agent"), 80)
    if agent:
        memory["latest_by_agent"][agent] = event
    if event.get("type") in {"agent_complete", "agent_blocked", "agent_backflow", "agent_recovered"}:
        memory["attempts"] = [*memory["attempts"], _attempt_record(event)][-MAX_ATTEMPTS:]
    if event.get("type") in {"agent_complete", "agent_note"}:
        memory["agent_notes"] = [*memory["agent_notes"], _agent_note(event)][-MAX_AGENT_NOTES:]
    if event.get("type") in {"agent_complete", "agent_handoff"}:
        memory["handoffs"] = [*memory["handoffs"], _handoff_record(event)][-MAX_HANDOFFS:]
    if event.get("type") in {"agent_blocked", "partial_recovery", "agent_backflow", "agent_recovered"}:
        memory["recovery_notes"] = [*memory["recovery_notes"], _recovery_record(event)][-MAX_RECOVERY_NOTES:]
    memory["updated_at"] = _utc_now()
    metadata["mission_memory"] = memory
    return metadata


def memory_patch_from_event(existing_metadata, event):
    return {"mission_memory": append_memory_event(existing_metadata, event)["mission_memory"]}


def memory_prompt_context(metadata, limit=8):
    memory = mission_memory_from_metadata(metadata)
    latest = list(memory.get("latest_by_agent", {}).values())[-limit:]
    return {
        "version": memory["version"],
        "status": memory["status"],
        "updated_at": memory.get("updated_at", ""),
        "latest_agent_notes": [
            {
                "agent": item.get("agent", ""),
                "type": item.get("type", ""),
                "attempt": item.get("attempt", 1),
                "summary": item.get("summary", ""),
                "next_action": item.get("next_action", ""),
                "quality_gate": item.get("quality_gate", {}),
            }
            for item in latest
            if isinstance(item, dict)
        ],
        "recent_recovery_notes": memory.get("recovery_notes", [])[-5:],
        "recent_handoffs": memory.get("handoffs", [])[-5:],
        "open_questions": memory.get("open_questions", [])[-10:],
    }


def final_artifact_contract_packet():
    return {
        "version": FINAL_ARTIFACT_CONTRACT_VERSION,
        "minimum_confidence": 0.96,
        "required_common_keys": [
            "summary",
            "commands_run",
            "files_inspected",
            "vault_sources_used",
            "confidence",
            "confidence_reason",
        ],
        "required_behavior": [
            "Return the stage JSON artifact in the final message.",
            "Record inspected files and commands instead of vague claims.",
            "If confidence is below 96%, inspect more evidence or mark the artifact blocked with a clear recovery action.",
            "Every completed stage writes memory, handoff, and quality-gate evidence.",
        ],
        "owner_review_rule": "No mission may be review-ready with missing final artifacts, missing test evidence, or unresolved blockers.",
    }


def partial_recovery_contract_packet():
    return {
        "version": PARTIAL_RECOVERY_VERSION,
        "purpose": "Convert failed, timed-out, or partial agent work into a recovery packet for the next attempt.",
        "recoverable_inputs": ["changed_files", "stdout_tail", "stderr_tail", "pr_links", "commit_refs", "agent_ledger"],
        "required_next_action": "Preserve useful partial work, identify the exact missing final artifact/evidence, and rerun only the required stage.",
    }


def parallel_agent_planning_packet(agent_order):
    agent_order = [_clean(agent, 80) for agent in _list(agent_order) if _clean(agent, 80)]
    read_only = [
        agent for agent in agent_order
        if agent in {
            "idea_expander",
            "concept_strategist",
            "product_architect",
            "visual_reference_interpreter",
            "creative_ui_designer",
            "ux_interaction_designer",
            "technical_architect",
            "source_mapper",
            "business_model_agent",
            "risk_agent",
        }
    ]
    write_agents = [
        agent for agent in agent_order
        if agent not in read_only and agent not in {"qa_red_team", "reviewer", "brain_guard", "evidence_reviewer", "security_reviewer", "business_reviewer", "product_reviewer", "visual_qa_reviewer"}
    ]
    review_agents = [
        agent for agent in agent_order
        if agent in {"qa_red_team", "reviewer", "brain_guard", "evidence_reviewer", "security_reviewer", "business_reviewer", "product_reviewer", "visual_qa_reviewer"}
    ]
    return {
        "version": PARALLEL_PLANNING_VERSION,
        "mode": "parallel_read_only_analysis_then_serialized_writes",
        "read_only_parallel_agents": read_only,
        "council_synthesis": "council_synthesis" if len(read_only) > 1 else "",
        "serialized_write_agents": write_agents,
        "review_and_challenge_agents": review_agents,
        "lock_policy": "Only one agent may write to repo files at a time; parallel agents may read, critique, and produce planning artifacts.",
        "handoff_policy": "Council synthesis resolves conflicts before builder/frontend implementation begins.",
    }


def replay_packet(mission):
    mission = mission if isinstance(mission, dict) else {}
    metadata = mission.get("metadata") if isinstance(mission.get("metadata"), dict) else {}
    review_packet = metadata.get("review_packet") if isinstance(metadata.get("review_packet"), dict) else {}
    agent_execution = metadata.get("agent_execution") if isinstance(metadata.get("agent_execution"), dict) else {}
    return {
        "version": "charlie_mission_replay_v1",
        "mission_id": mission.get("mission_id", ""),
        "title": mission.get("title", ""),
        "status": mission.get("status", ""),
        "mission_memory": mission_memory_from_metadata(metadata),
        "agent_execution": agent_execution,
        "review_packet": review_packet,
        "timeline": _timeline(metadata, agent_execution, review_packet),
        "debug_focus": {
            "blocked_agent": review_packet.get("blocked_agent", ""),
            "blocked_reason": review_packet.get("blocked_reason", ""),
            "unresolved_blockers": review_packet.get("unresolved_blockers", []),
            "quality_gates": review_packet.get("quality_gates", []),
            "backflow_events": review_packet.get("backflow_events", []),
        },
        "next_debug_actions": _next_debug_actions(review_packet),
    }


def _timeline(metadata, agent_execution, review_packet):
    events = []
    memory = mission_memory_from_metadata(metadata)
    for item in memory.get("events", []):
        if isinstance(item, dict):
            events.append({
                "time": item.get("recorded_at", ""),
                "type": item.get("type", "memory"),
                "agent": item.get("agent", ""),
                "summary": item.get("summary", ""),
            })
    for item in _list(agent_execution.get("stages")):
        if isinstance(item, dict):
            events.append({
                "time": item.get("updated_at") or item.get("started_at") or "",
                "type": f"stage_{item.get('status', 'unknown')}",
                "agent": item.get("agent", ""),
                "summary": item.get("current_action") or item.get("status", ""),
            })
    for item in _list(review_packet.get("backflow_events")):
        if isinstance(item, dict):
            events.append({
                "time": item.get("recorded_at", ""),
                "type": "backflow",
                "agent": item.get("from_agent", ""),
                "summary": item.get("reason", ""),
            })
    return sorted(events, key=lambda item: item.get("time", ""))[-120:]


def _next_debug_actions(review_packet):
    if not review_packet:
        return ["No review packet yet. Check runner status and mission memory."]
    if review_packet.get("blocked_reason"):
        return [
            "Inspect blocked artifact and stdout/stderr tails.",
            "Use recovery notes to rerun from the blocked or upstream stage.",
            "Convert repeated blocker into an improvement proposal if it appears twice.",
        ]
    if review_packet.get("review_status") == "ready_for_owner_review":
        return ["Owner can review release evidence, visual evidence, and final artifacts before approval."]
    return ["Inspect replay timeline and verify final artifact contract evidence."]


def _attempt_record(event):
    return {
        "agent": event.get("agent", ""),
        "attempt": event.get("attempt", 1),
        "type": event.get("type", ""),
        "summary": event.get("summary", ""),
        "quality_gate": event.get("quality_gate", {}),
        "recorded_at": event.get("recorded_at", ""),
    }


def _agent_note(event):
    return {
        "agent": event.get("agent", ""),
        "summary": event.get("summary", ""),
        "next_action": event.get("next_action", ""),
        "confidence": event.get("confidence", ""),
        "recorded_at": event.get("recorded_at", ""),
    }


def _handoff_record(event):
    return {
        "from_agent": event.get("agent", ""),
        "summary": event.get("summary", ""),
        "next_action": event.get("next_action", ""),
        "changed_files": event.get("changed_files", []),
        "tests_run": event.get("tests_run", []),
        "recorded_at": event.get("recorded_at", ""),
    }


def _recovery_record(event):
    return {
        "agent": event.get("agent", ""),
        "type": event.get("type", ""),
        "summary": event.get("summary", ""),
        "recovery": event.get("recovery", {}),
        "next_action": event.get("next_action", ""),
        "recorded_at": event.get("recorded_at", ""),
    }


def _clean_list(value, limit=20, text_limit=260):
    return [_clean(item, text_limit) for item in _list(value)[:limit] if _clean(item, text_limit)]


def _list(value):
    return value if isinstance(value, list) else ([] if value in (None, "") else [value])


def _clean(value, limit=MAX_TEXT):
    text = str(value or "").strip()
    return text[:limit]


def _int(value, default):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _utc_now():
    return datetime.now(timezone.utc).isoformat()
