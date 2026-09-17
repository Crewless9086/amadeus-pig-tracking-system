"""Deterministic governance for CHARLIE approvals, evaluations, and research."""

from __future__ import annotations

from datetime import datetime, timezone

from modules.charlie.executive_control import RED_ZONE_TERMS, stable_fingerprint


def build_approval_bundle(goal_id, decisions):
    """Collapse related decisions into one auditable owner approval request."""
    normalized = []
    for item in decisions or []:
        if not isinstance(item, dict):
            continue
        risk_flags = sorted({str(value).strip().lower() for value in item.get("risk_flags", []) if str(value).strip()})
        normalized.append({
            "decision_id": str(item.get("decision_id") or stable_fingerprint(item)),
            "title": str(item.get("title") or "Decision required"),
            "recommended_action": str(item.get("recommended_action") or "review"),
            "risk_flags": risk_flags,
            "evidence": item.get("evidence") if isinstance(item.get("evidence"), dict) else {},
            "rollback": str(item.get("rollback") or ""),
        })
    red_flags = sorted({flag for item in normalized for flag in item["risk_flags"] if flag in RED_ZONE_TERMS})
    bundle_id = "APPROVAL-" + stable_fingerprint({"goal_id": goal_id, "decisions": normalized}).upper()
    return {
        "version": "charlie_approval_bundle_v1",
        "bundle_id": bundle_id,
        "goal_id": str(goal_id or ""),
        "owner_action_required": bool(normalized),
        "authority_tier": "charl_human",
        "red_zone_flags": red_flags,
        "decisions": normalized,
        "summary": f"Review {len(normalized)} related decision(s) once.",
    }


def evaluate_mission_class(eval_spec, evidence):
    spec = eval_spec if isinstance(eval_spec, dict) else {}
    evidence = evidence if isinstance(evidence, dict) else {}
    scenarios = spec.get("scenarios") if isinstance(spec.get("scenarios"), list) else []
    required_gates = spec.get("required_gates") if isinstance(spec.get("required_gates"), list) else []
    scenario_results = evidence.get("scenarios") if isinstance(evidence.get("scenarios"), dict) else {}
    gate_results = evidence.get("gates") if isinstance(evidence.get("gates"), dict) else {}
    passed = sum(1 for scenario in scenarios if scenario_results.get(str(scenario)) is True)
    rate = passed / len(scenarios) if scenarios else 0.0
    missing_gates = [str(gate) for gate in required_gates if gate_results.get(str(gate)) is not True]
    minimum = float(spec.get("minimum_pass_rate") if spec.get("minimum_pass_rate") is not None else 1.0)
    reasons = []
    if not scenarios:
        reasons.append("eval_scenarios_missing")
    if rate < minimum:
        reasons.append("minimum_pass_rate_not_met")
    if missing_gates:
        reasons.append("required_gates_not_met")
    return {
        "passed": not reasons,
        "pass_rate": round(rate, 4),
        "minimum_pass_rate": minimum,
        "missing_gates": missing_gates,
        "reasons": reasons,
    }


def research_observation(*, business_area, topic, source_url, source_kind="primary", summary="", applicability="unreviewed", observed_at=None):
    source_url = str(source_url or "").strip()
    if not source_url.startswith(("https://", "http://")):
        return {"accepted": False, "reason": "source_url_required"}
    if str(source_kind or "").lower() not in {"primary", "official", "research", "industry"}:
        return {"accepted": False, "reason": "unsupported_source_kind"}
    observed_at = observed_at or datetime.now(timezone.utc)
    payload = {
        "business_area": str(business_area or "system").strip(),
        "topic": str(topic or "").strip(),
        "source_url": source_url,
        "source_kind": str(source_kind).lower(),
        "summary": str(summary or "").strip(),
        "applicability": str(applicability or "unreviewed").strip(),
        "observed_at": observed_at.isoformat(),
        "auto_activate": False,
        "owner_review_required": True,
    }
    payload["research_id"] = "RESEARCH-" + stable_fingerprint(payload).upper()
    return {"accepted": bool(payload["topic"]), "reason": "record_only_owner_review_required", "observation": payload}
