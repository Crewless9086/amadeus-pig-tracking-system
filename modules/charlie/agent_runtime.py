"""Shared governed runtime for CHARLIE's operational domain agents."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from time import monotonic
from typing import Callable
import uuid


@dataclass(frozen=True)
class AgentDefinition:
    agent_id: str
    name: str
    domain: str
    authority_tier: str
    capabilities: tuple[str, ...]
    source_contract: tuple[str, ...]
    handler: Callable
    repair_handler: Callable | None = None


_REGISTRY: dict[str, AgentDefinition] = {}


def register_agent(definition):
    if not isinstance(definition, AgentDefinition) or not definition.agent_id.strip():
        raise ValueError("valid_agent_definition_required")
    if definition.authority_tier not in {"read_only", "prepare_only", "owner_gated"}:
        raise ValueError("agent_authority_tier_invalid")
    _REGISTRY[definition.agent_id] = definition
    return definition


def registered_agents():
    _ensure_defaults()
    return [{
        "agent_id": item.agent_id,
        "name": item.name,
        "domain": item.domain,
        "authority_tier": item.authority_tier,
        "capabilities": list(item.capabilities),
        "source_contract": list(item.source_contract),
    } for item in sorted(_REGISTRY.values(), key=lambda row: row.agent_id)]


def delegate_to_agent(agent_id, request, *, intent_id="", recorder=None, event_sink=None):
    _ensure_defaults()
    definition = _REGISTRY.get(str(agent_id or "").strip())
    if not definition:
        return {"success": False, "status": "agent_not_registered", "agent_id": str(agent_id or "")}, 404
    request = _normalize_request(request, definition)
    run_id = "ARUN-" + uuid.uuid4().hex.upper()
    started = monotonic()
    if event_sink:
        event_sink("agent_delegated", {"agent_id": definition.agent_id, "agent_name": definition.name, "domain": definition.domain, "goal": request["goal"][:240]})
    try:
        result = definition.handler(request)
        result = result if isinstance(result, dict) else {}
    except Exception as exc:
        result = {"success": False, "status": "agent_execution_failed", "error_type": exc.__class__.__name__, "unresolved_questions": ["The authoritative agent source could not be read."]}
    sufficient, gaps = assess_evidence(result)
    repaired = False
    if not sufficient and definition.repair_handler:
        repaired = True
        try:
            repair = definition.repair_handler(request, result, gaps)
            if isinstance(repair, dict):
                result = repair
        except Exception as exc:
            result.setdefault("repair_error_type", exc.__class__.__name__)
        sufficient, gaps = assess_evidence(result)
    duration_ms = round((monotonic() - started) * 1000)
    success = result.get("success") is not False and sufficient
    resolved_capability = str(result.get("capability") or request.get("capability") or "investigate")
    packet = {
        **result,
        "success": success,
        "status": "agent_evidence_ready" if success else result.get("status") or "agent_evidence_insufficient",
        "agent": {
            "agent_id": definition.agent_id, "name": definition.name, "domain": definition.domain,
            "authority_tier": definition.authority_tier, "run_id": run_id,
            "capability": resolved_capability, "duration_ms": duration_ms,
            "evidence_sufficient": sufficient, "evidence_gaps": gaps, "repair_attempted": repaired,
        },
        "observed_at": datetime.now(timezone.utc).isoformat(),
        "write_authority": False,
    }
    status_code = 200 if success else 422 if result.get("success") is not False else 503
    if recorder and intent_id:
        recorder(intent_id, f"agent.{definition.agent_id}.{resolved_capability}", definition.authority_tier, request, packet, status="succeeded" if success else "failed")
    if event_sink:
        event_sink("agent_completed", {"agent_id": definition.agent_id, "success": success, "status": packet["status"], "duration_ms": duration_ms, "evidence_gaps": gaps})
    return packet, status_code


def assess_evidence(result):
    if not isinstance(result, dict) or result.get("success") is False:
        return False, ["agent_result_unavailable"]
    gaps = []
    if result.get("direct_answer") in (None, ""):
        gaps.append("direct_answer_missing")
    if not result.get("sources"):
        gaps.append("source_provenance_missing")
    if not result.get("freshness"):
        gaps.append("freshness_missing")
    if float(result.get("confidence") or 0) < 0.8:
        gaps.append("confidence_below_0_80")
    unresolved = [str(value) for value in (result.get("unresolved_questions") or []) if str(value).strip()]
    if unresolved and result.get("direct_answer") in (None, ""):
        gaps.append("unresolved_answer_blocker")
    return not gaps, gaps


def _normalize_request(request, definition):
    source = request if isinstance(request, dict) else {}
    return {
        "request_id": str(source.get("request_id") or "AREQ-" + uuid.uuid4().hex.upper()),
        "goal": str(source.get("goal") or source.get("question") or "Investigate the current domain truth")[:1500],
        "question": str(source.get("question") or source.get("goal") or "")[:3000],
        "capability": str(source.get("capability") or "investigate")[:120],
        "subject": source.get("subject") if isinstance(source.get("subject"), dict) else {},
        "known_context": source.get("known_context") if isinstance(source.get("known_context"), dict) else {},
        "authority": "read_only" if definition.authority_tier == "read_only" else definition.authority_tier,
        "required_freshness": str(source.get("required_freshness") or "live")[:80],
    }


def _ensure_defaults():
    if "herdmaster" not in _REGISTRY:
        from modules.agents.herdmaster import HERDMASTER_DEFINITION
        register_agent(HERDMASTER_DEFINITION)
