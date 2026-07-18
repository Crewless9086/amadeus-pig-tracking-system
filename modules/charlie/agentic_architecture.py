"""Frozen agent-first architecture contract for CHARLIE CORE missions."""

from __future__ import annotations

import re


CONTRACT_VERSION = "charlie_agentic_architecture_v1"
DOMAIN_OWNERS = {
    "farm": {"agent": "oom-sakkie", "specialists": ["herdmaster", "quartermaster", "rootline", "gatekeeper"]},
    "livestock_sales": {"agent": "sam-live-stock", "specialists": ["herdmaster", "ledger"]},
    "meat_sales": {"agent": "sam-meat", "specialists": ["butcher", "ledger"]},
    "marketing": {"agent": "beacon", "specialists": ["sam-live-stock", "sam-meat", "ledger"]},
    "transport": {"agent": "fred", "specialists": ["ledger"]},
    "engineering": {"agent": "charlie-core", "specialists": ["analyst"]},
}


def build_agentic_architecture_packet(mission):
    mission = mission if isinstance(mission, dict) else {}
    text = " ".join(str(mission.get(key) or "") for key in ("mission_type", "title", "raw_text")).lower()
    domain = _domain(text)
    ownership = DOMAIN_OWNERS[domain]
    reasoning = domain != "engineering"
    return {
        "version": CONTRACT_VERSION,
        "status": "frozen_before_builder",
        "business_outcome": str(mission.get("title") or mission.get("raw_text") or mission.get("mission_type") or "Bounded system outcome")[:500],
        "domain": domain,
        "owning_agent": ownership["agent"],
        "coordinating_agent": "charlie" if domain != "farm" else "oom-sakkie",
        "supporting_agents": list(ownership["specialists"]),
        "reasoning_owner_required": reasoning,
        "canonical_data_required": domain != "engineering",
        "deterministic_code_roles": ["canonical reads", "calculations", "validation", "permissions", "idempotency", "audit", "safe execution"],
        "agent_roles": ["interpret intent", "reason over evidence", "reconcile uncertainty", "recommend next action", "communicate naturally"],
        "prohibited_designs": [
            "question-specific CHARLIE handler when a domain agent owns the outcome",
            "business reasoning embedded in UI, route, regex, or transport code",
            "parallel mission or shadow source-of-truth system",
            "model output bypassing deterministic verification or authority policy",
        ],
        "evidence_contract": ["direct_answer", "facts", "sources", "freshness", "confidence", "authority"],
        "acceptance_questions": [
            "Which operational agent becomes more capable?",
            "What canonical evidence does that agent use?",
            "What reasoning belongs to the agent?",
            "What deterministic code is genuinely required?",
            "How is generalization beyond the original example proven?",
        ],
        "learning_signals": ["clean evidence rate", "owner correction rate", "adjacent-question pass rate", "false escalation rate", "latency"],
        "authority_rule": "Agent reasoning never expands write authority; protected actions use existing audited rails.",
    }


def evaluate_agentic_architecture(mission, artifacts=None):
    artifacts = artifacts if isinstance(artifacts, dict) else {}
    metadata = (mission or {}).get("metadata") if isinstance((mission or {}).get("metadata"), dict) else {}
    core = metadata.get("charlie_core") if isinstance(metadata.get("charlie_core"), dict) else {}
    packet = metadata.get("agentic_architecture") if isinstance(metadata.get("agentic_architecture"), dict) else {}
    if not packet:
        packet = core.get("agentic_architecture") if isinstance(core.get("agentic_architecture"), dict) else {}
    if not packet:
        truth = core.get("project_truth") if isinstance(core.get("project_truth"), dict) else {}
        packet = truth.get("agentic_architecture") if isinstance(truth.get("agentic_architecture"), dict) else {}
    findings = []
    if packet.get("version") != CONTRACT_VERSION:
        findings.append("Frozen Agentic Architecture Packet is missing or stale.")
    if not packet.get("owning_agent"):
        findings.append("Mission has no operational owning agent.")
    if packet.get("reasoning_owner_required") and not packet.get("supporting_agents"):
        findings.append("Domain reasoning mission has no specialist evidence path.")
    for agent in ("technical_architect", "architect", "builder", "reviewer", "evidence_reviewer"):
        artifact = artifacts.get(agent)
        if not isinstance(artifact, dict):
            continue
        compliance = artifact.get("agentic_architecture") if isinstance(artifact.get("agentic_architecture"), dict) else {}
        if compliance.get("compliant") is False:
            findings.append(f"{agent} reported agentic architecture non-compliance: {compliance.get('reason') or 'reason missing'}")
    return {"version": CONTRACT_VERSION, "passed": not findings, "findings": findings, "packet": packet}


def architecture_drift_signals(mission):
    texts = []
    metadata = (mission or {}).get("metadata") if isinstance((mission or {}).get("metadata"), dict) else {}
    packet = metadata.get("review_packet") if isinstance(metadata.get("review_packet"), dict) else {}
    texts.extend(str(value or "") for value in packet.get("errors") or [])
    texts.extend(str(value or "") for value in packet.get("qa_findings") or [])
    combined = " ".join(texts).lower()
    patterns = {
        "leaf_handler_drift": r"question[- ]specific|special[- ]case|one[- ]off handler|reply branch",
        "reasoning_in_transport": r"business reasoning.*(?:route|ui|regex|transport)|regex.*business logic",
        "agent_bypass": r"bypass(?:ed|ing)? (?:the )?(?:domain )?agent|direct service call.*instead of.*agent",
        "shadow_truth": r"shadow (?:state|truth|database)|parallel mission system",
    }
    return [name for name, pattern in patterns.items() if re.search(pattern, combined)]


def _domain(text):
    if re.search(r"\b(sam|livestock|live stock|customer|quote|sales conversation)\b", text):
        return "livestock_sales"
    if re.search(r"\b(meat|butcher|carcass|cuts|slaughter)\b", text):
        return "meat_sales"
    if re.search(r"\b(beacon|marketing|campaign|facebook|post|media)\b", text):
        return "marketing"
    if re.search(r"\b(fred|transport|booking|driver|route)\b", text):
        return "transport"
    if re.search(r"\b(farm|pig|litter|herd|feed|irrigation|weather|power)\b", text):
        return "farm"
    return "engineering"
