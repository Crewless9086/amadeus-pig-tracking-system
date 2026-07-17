"""Deterministic, advisory-only Beacon autonomy readiness projection."""

from datetime import datetime, timedelta, timezone
import hashlib
import json


POLICY_BODY = {
    "policy_id": "beacon_advisory_readiness_v1",
    "authority_state": "owner_approved",
    "campaigns": {"minimum": 10, "minimum_weeks": 6},
    "unedited_approvals": {"minimum": 10, "minimum_rate": 0.85},
    "attribution": {"minimum_rate": 0.95},
    "recommendations": {"minimum": 10, "minimum_accuracy": 0.80},
    "safety": {"lookback_days": 90, "maximum_high_or_critical": 0, "maximum_unresolved": 0},
    "trust": {"minimum_clean_weeks": 8},
    "budget": {"minimum_compliance": 1.0},
}
POLICY_HASH = hashlib.sha256(json.dumps(POLICY_BODY, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
APPROVED_POLICY = {**POLICY_BODY, "content_hash": POLICY_HASH}

AUTHORITY = {
    "posts_publicly": False,
    "calls_meta": False,
    "boosts_post": False,
    "spends_money": False,
    "approval_executes_action": False,
    "separate_owner_gate_required": True,
}


def evaluate_beacon_advisory_readiness(evidence=None, policy=None, prior_evaluations=None, now=None):
    """Project readiness from canonical evidence; never execute a promoted action."""
    evidence = evidence if isinstance(evidence, dict) else {}
    policy = policy if isinstance(policy, dict) else APPROVED_POLICY
    prior_evaluations = prior_evaluations if isinstance(prior_evaluations, list) else []
    now = _time(now)
    policy_error = _policy_error(policy, now)
    gates = _blocked_gates(policy_error) if policy_error else {
        "campaign_evidence": _campaign_gate(evidence.get("campaigns"), policy, now),
        "unedited_approval_rate": _approval_gate(evidence.get("approvals"), policy, now),
        "attribution_completeness": _attribution_gate(evidence.get("attributions"), policy, now),
        "recommendation_accuracy": _recommendation_gate(evidence.get("recommendations"), policy, now),
        "safety_incidents": _safety_gate(evidence.get("incidents"), policy, now),
        "trust_history": _trust_gate(evidence.get("trust_weeks"), policy, now),
        "budget_compliance": _budget_gate(evidence.get("budgets"), policy, now),
    }
    ready = not policy_error and all(gate["status"] == "passed" for gate in gates.values())
    previous_ready = bool(prior_evaluations and prior_evaluations[-1].get("ready"))
    state = "ready_for_owner_review" if ready else ("suspended" if previous_ready else "not_ready")
    snapshot = {"policy_hash": policy.get("content_hash", ""), "evaluated_at": now.isoformat(), "gates": gates}
    evaluation_id = _digest(snapshot)
    transition = "threshold_met" if ready and not previous_ready else "readiness_suspended" if previous_ready and not ready else "unchanged"
    notification = None
    if transition != "unchanged":
        notification_key = f"{policy.get('content_hash','')}:{transition}:{evaluation_id}"
        already_recorded = any(item.get("notification_key") == notification_key for item in prior_evaluations)
        if not already_recorded:
            notification = {
                "notification_key": notification_key,
                "owner_only": True,
                "type": transition,
                "status": "prepared",
                "message": "Beacon advisory readiness met; owner promotion review required." if ready else "Beacon advisory readiness regressed and is suspended.",
            }
    return {
        "schema_version": "beacon_advisory_readiness_projection_v1",
        "success": True,
        "policy": {"policy_id": policy.get("policy_id", ""), "authority_state": policy.get("authority_state", ""), "content_hash": policy.get("content_hash", "")},
        "evaluation_id": evaluation_id,
        "evaluated_at": now.isoformat(),
        "state": state,
        "ready": ready,
        "transition": transition,
        "notification": notification,
        "gates": gates,
        "promotion_scope": "advisory_drafting_and_recommendation_preparation_only",
        "authority": dict(AUTHORITY),
    }


def _base(key, numerator, denominator, minimum, window, lineage, status, reason, freshness="fresh"):
    return {"metric": key, "numerator": numerator, "denominator": denominator, "minimum_sample": minimum,
            "evaluation_window": window, "freshness": freshness, "evidence_lineage": lineage,
            "threshold": None, "status": status, "reason": reason}


def _campaign_gate(rows, policy, now):
    rows = _latest(rows)
    eligible = [r for r in rows if r.get("status") == "completed" and _fresh(r, now, 42)]
    weeks = {str(r.get("completed_at", ""))[:10] for r in eligible}
    result = _base("campaign_evidence", len(eligible), len(rows), policy["campaigns"]["minimum"], "6_weeks", _ids(eligible), "failed", "insufficient_campaign_evidence")
    result["threshold"] = {"campaigns": 10, "calendar_weeks": 6}
    if len(eligible) >= 10 and len({w[:7] + "-" + str(_time(w).isocalendar().week) for w in weeks}) >= 6:
        result.update(status="passed", reason="threshold_met")
    return result


def _approval_gate(rows, policy, now):
    rows = [r for r in _latest(rows) if _fresh(r, now, 42)]
    known = [r for r in rows if r.get("proposed_hash") and r.get("approved_hash") and r.get("edit_classification") in {"unedited", "edited"}]
    unedited = sum(r["proposed_hash"] == r["approved_hash"] and r["edit_classification"] == "unedited" for r in known)
    rate = unedited / len(known) if known else 0
    result = _base("unedited_approval_rate", unedited, len(known), 10, "6_weeks", _ids(known), "failed", "insufficient_or_edited_approval_evidence")
    result["threshold"] = 0.85
    if len(known) >= 10 and rate >= 0.85: result.update(status="passed", reason="threshold_met")
    return result


def _attribution_gate(rows, policy, now):
    rows = [r for r in _latest(rows) if _fresh(r, now, 42)]
    complete = sum(bool(r.get("disposition") == "complete" and r.get("campaign_id") and r.get("source_ref")) for r in rows)
    rate = complete / len(rows) if rows else 0
    result = _base("attribution_completeness", complete, len(rows), 10, "6_weeks", _ids(rows), "failed", "incomplete_or_unavailable_attribution")
    result["threshold"] = 0.95
    if len(rows) >= 10 and rate >= 0.95: result.update(status="passed", reason="threshold_met")
    return result


def _recommendation_gate(rows, policy, now):
    rows = [r for r in _latest(rows) if r.get("matured") is True and _fresh(r, now, 42)]
    accurate = sum(_server_recommendation(r) == r.get("outcome_label") for r in rows)
    rate = accurate / len(rows) if rows else 0
    result = _base("recommendation_accuracy", accurate, len(rows), 10, "6_weeks", _ids(rows), "failed", "insufficient_or_inaccurate_recommendations")
    result["threshold"] = 0.80
    if len(rows) >= 10 and rate >= 0.80: result.update(status="passed", reason="threshold_met")
    return result


def _safety_gate(rows, policy, now):
    rows = [r for r in _latest(rows) if _fresh(r, now, 90)]
    controlled = [r for r in rows if r.get("severity") in {"low", "medium", "high", "critical"} and isinstance(r.get("resolved"), bool)]
    high = sum(r["severity"] in {"high", "critical"} for r in controlled)
    unresolved = sum(not r["resolved"] for r in controlled)
    result = _base("safety_incidents", 0 if not controlled else high + unresolved, len(controlled), 1, "90_days", _ids(controlled), "failed", "missing_or_disqualifying_incident_history")
    result["threshold"] = {"high_or_critical": 0, "unresolved": 0}
    if controlled and high == 0 and unresolved == 0: result.update(status="passed", reason="threshold_met")
    return result


def _trust_gate(rows, policy, now):
    rows = [r for r in _latest(rows) if _fresh(r, now, 56) and r.get("evaluated") is True]
    clean = sum(r.get("clean") is True and not r.get("authority_breach") for r in rows)
    result = _base("trust_history", clean, len(rows), 8, "8_weeks", _ids(rows), "failed", "insufficient_or_regressed_trust_history")
    result["threshold"] = 8
    if len(rows) >= 8 and clean == len(rows): result.update(status="passed", reason="threshold_met")
    return result


def _budget_gate(rows, policy, now):
    rows = [r for r in _latest(rows) if _fresh(r, now, 42)]
    compatible = [r for r in rows if r.get("authority_state") == "owner_approved" and r.get("currency") and r.get("window") and r.get("actual_spend") is not None and r.get("cap") is not None]
    compliant = sum(float(r["actual_spend"]) <= float(r["cap"]) for r in compatible)
    result = _base("budget_compliance", compliant, len(rows), 10, "6_weeks", _ids(compatible), "failed", "missing_incompatible_or_over_budget")
    result["threshold"] = 1.0
    if len(rows) >= 10 and len(compatible) == len(rows) and compliant == len(rows): result.update(status="passed", reason="threshold_met")
    return result


def _policy_error(policy, now):
    if policy.get("authority_state") != "owner_approved": return "policy_not_owner_approved"
    if policy.get("expires_at") and _time(policy["expires_at"]) <= now: return "policy_expired"
    if policy.get("superseded_by"): return "policy_superseded"
    supplied = policy.get("content_hash", "")
    body = {k: v for k, v in policy.items() if k != "content_hash"}
    if supplied != _digest(body): return "policy_malformed"
    return ""


def _blocked_gates(reason):
    return {key: _base(key, 0, 0, 0, "unavailable", [], "blocked", reason, "unavailable") for key in
            ("campaign_evidence", "unedited_approval_rate", "attribution_completeness", "recommendation_accuracy", "safety_incidents", "trust_history", "budget_compliance")}


def _latest(rows):
    rows = rows if isinstance(rows, list) else []
    current = {}
    for row in rows:
        if not isinstance(row, dict) or not row.get("evidence_id"): continue
        current[row["evidence_id"]] = row
    superseded = {r.get("supersedes") for r in current.values() if r.get("supersedes")}
    return [r for key, r in current.items() if key not in superseded and not r.get("superseded_by")]


def _server_recommendation(row):
    score = row.get("outcome_score")
    return "accurate" if isinstance(score, (int, float)) and score >= 0.5 else "inaccurate"


def _fresh(row, now, days):
    try: return _time(row.get("observed_at")) >= now - timedelta(days=days)
    except (TypeError, ValueError): return False


def _ids(rows): return [r["evidence_id"] for r in rows]
def _digest(value): return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
def _time(value):
    if isinstance(value, datetime): return value.astimezone(timezone.utc)
    if not value: return datetime.now(timezone.utc)
    return datetime.fromisoformat(str(value).replace("Z", "+00:00")).astimezone(timezone.utc)
