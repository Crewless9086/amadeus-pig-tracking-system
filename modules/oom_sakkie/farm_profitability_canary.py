"""Read-only cross-agent evidence reconciliation for farm canaries.

This is deliberately a pure function.  It accepts evidence already read by
the named operational agents and cannot dispatch a tool, persist an order, or
alter a farm record.  Oom Sakkie owns the resulting advisory packet.
"""

from __future__ import annotations


REQUIRED_AGENTS = ("herdmaster", "ledger", "oom-sakkie")
FORBIDDEN_ACTIONS = (
    "create_order", "customer_send", "payment", "reserve_stock",
    "farm_lifecycle_write", "pig_record_write",
)


def reconcile_farm_profitability_canary(*, observation: dict, evidence_by_agent: dict) -> dict:
    """Return attributable agreement evidence or fail closed with questions.

    An observation is factual input.  The generated intent is advisory only;
    it never becomes a farm or commercial instruction.  Each required agent
    must provide an evidence envelope with provenance, freshness, authority,
    and an advisory recommendation before agreement can be reported.
    """
    observation = observation if isinstance(observation, dict) else {}
    evidence_by_agent = evidence_by_agent if isinstance(evidence_by_agent, dict) else {}
    observation_packet = _observation_packet(observation)
    packets, gaps = {}, list(observation_packet["gaps"])

    for agent in REQUIRED_AGENTS:
        packet, packet_gaps = _evidence_packet(agent, evidence_by_agent.get(agent))
        packets[agent] = packet
        gaps.extend(packet_gaps)

    recommendations = {
        agent: packet["recommendation"]
        for agent, packet in packets.items()
        if packet["recommendation"]
    }
    distinct = sorted(set(recommendations.values()))
    agreement = not gaps and len(distinct) == 1
    disagreement = len(distinct) > 1
    status = "agreement_ready" if agreement else "reconciliation_required"

    return {
        "success": agreement,
        "status": status,
        "owner_agent": "oom-sakkie",
        "mode": "production_read_only_advisory",
        "observation": observation_packet,
        "intent": {
            "value": "review_farm_profitability_evidence",
            "derived_from_observation": True,
            "advisory_only": True,
            "may_execute": False,
        },
        "agent_evidence": packets,
        "agreement": {
            "reached": agreement,
            "recommendation": distinct[0] if agreement else "",
            "disagreement_detected": disagreement,
            "recommendations_by_agent": recommendations,
        },
        "unresolved_questions": _unique(gaps) + (
            ["Agents disagree; reconcile canonical evidence before any owner decision."] if disagreement else []
        ),
        "authority": {
            "writes": False,
            "commercial_action": "none",
            "forbidden_actions": list(FORBIDDEN_ACTIONS),
        },
    }


def _observation_packet(observation):
    facts = observation.get("facts")
    source = str(observation.get("source") or "").strip()
    observed_at = str(observation.get("observed_at") or "").strip()
    gaps = []
    if not isinstance(facts, list) or not facts:
        gaps.append("Observation must contain at least one factual item.")
    if not source:
        gaps.append("Observation source is required for attribution.")
    if not observed_at:
        gaps.append("Observation timestamp is required for freshness.")
    return {"facts": facts if isinstance(facts, list) else [], "source": source,
            "observed_at": observed_at, "gaps": gaps}


def _evidence_packet(agent, evidence):
    evidence = evidence if isinstance(evidence, dict) else {}
    source = str(evidence.get("source") or "").strip()
    observed_at = str(evidence.get("observed_at") or "").strip()
    authority = str(evidence.get("authority") or "").strip()
    recommendation = str(evidence.get("recommendation") or "").strip()
    gaps = []
    if not source:
        gaps.append(f"{agent} source is required for attribution.")
    if not observed_at:
        gaps.append(f"{agent} evidence timestamp is required for freshness.")
    if authority != "read_only":
        gaps.append(f"{agent} evidence must declare read_only authority.")
    if not recommendation:
        gaps.append(f"{agent} advisory recommendation is required.")
    return {
        "agent": agent, "source": source, "observed_at": observed_at,
        "authority": authority, "recommendation": recommendation,
        "facts": evidence.get("facts") if isinstance(evidence.get("facts"), list) else [],
    }, gaps


def _unique(items):
    return list(dict.fromkeys(items))
