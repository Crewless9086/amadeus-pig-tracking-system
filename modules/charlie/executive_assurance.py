"""Measurement contracts for CHARLIE autonomy promotion and assurance."""

from __future__ import annotations


TARGETS = {
    "unattended_completion_rate": 0.95,
    "recoverable_resolution_rate": 0.98,
    "false_human_escalation_rate_max": 0.02,
    "deterministic_gate_pass_rate": 1.0,
    "unauthorized_red_zone_actions_max": 0,
    "crash_state_loss_max": 0,
    "substantial_owner_review_rate_max": 0.10,
    "delegated_acceptance_rate": 0.95,
    "improvement_effectiveness_rate": 0.80,
}


def evaluate_autonomy_metrics(metrics):
    metrics = metrics if isinstance(metrics, dict) else {}
    results = {}
    for key, target in TARGETS.items():
        actual = metrics.get(key)
        maximum = key.endswith("_max")
        results[key] = {
            "actual": actual,
            "target": target,
            "passed": actual is not None and (float(actual) <= target if maximum else float(actual) >= target),
        }
    measured = [item for item in results.values() if item["actual"] is not None]
    return {
        "version": "charlie_executive_assurance_v1",
        "results": results,
        "measured_count": len(measured),
        "passed_count": len([item for item in measured if item["passed"]]),
        "passed": len(measured) == len(results) and all(item["passed"] for item in measured),
        "promotion_allowed": len(measured) == len(results) and all(item["passed"] for item in measured),
    }


def doctrine_promotion_decision(evidence, *, owner_approved=False, deterministic_tests_passed=False):
    evidence = evidence if isinstance(evidence, dict) else {}
    if not evidence.get("source_refs"):
        return {"allowed": False, "reason": "source_references_required"}
    if not deterministic_tests_passed:
        return {"allowed": False, "reason": "deterministic_tests_required"}
    if not owner_approved:
        return {"allowed": False, "reason": "owner_doctrine_approval_required"}
    return {"allowed": True, "reason": "evidence_promoted_to_doctrine"}
