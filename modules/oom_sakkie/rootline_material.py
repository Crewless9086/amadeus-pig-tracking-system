"""Stable owner-visible ROOTLINE decision material shared by daily/change rails."""
import hashlib
import json
import re
from typing import Any, Mapping


def rootline_material_digest(result: Mapping[str, Any]) -> str:
    lifecycles = result.get("irrigation_lifecycle")
    lifecycles = lifecycles if isinstance(lifecycles, Mapping) else {}
    recommendations = []
    for row in result.get("recommendations") or ():
        if not isinstance(row, Mapping):
            continue
        subject = str(row.get("subject") or "")
        # The standalone owner plan renders only the two irrigation zones.
        # Hidden borehole, power and fertilizer recommendation churn must not
        # manufacture a visibly identical Telegram plan every reassessment.
        if subject not in {"B12345", "C12345"}:
            continue
        lifecycle = lifecycles.get(subject)
        lifecycle = lifecycle if isinstance(lifecycle, Mapping) else {}
        item = {key: _normal(row.get(key)) for key in
                ("subject", "status", "recommendation", "preferred_window",
                 "planned_duration_minutes")}
        item["lifecycle_state"] = _normal(lifecycle.get("state"))
        item["verified_completion"] = _verified_completion(lifecycle, subject)
        item["owner_reason"] = owner_reason_material(row.get("reason"))
        recommendations.append(item)
    recommendations.sort(key=lambda row: (str(row.get("subject") or ""),
                                           str(row.get("status") or row.get("recommendation") or "")))
    selected = {"recommendations": recommendations,
        "next_reassessment": stable_reassessment(result.get("next_reassessment")),
        "owner_question": _owner_question((result.get("owner_brief") or {}).get("family_fact_needed"))}
    return hashlib.sha256(json.dumps(selected, sort_keys=True, separators=(",", ":"),
                                     default=str).encode()).hexdigest()


def stable_reassessment(value):
    if not isinstance(value, Mapping):
        return value
    trigger = str(value.get("trigger") or "")
    stable = {key: _normal(value.get(key)) for key in (
        "trigger", "reason", "also_on", "recovery_if_window_is_missed", "automatic_command"
    ) if key in value}
    if trigger not in {
        "canonical_plan_reassessment",
        "durable_backend_schedule",
        "new_canonical_evidence",
        "new_canonical_evidence_or_next_read",
        "refresh_missing_or_stale_evidence",
    } and "at" in value:
        stable["at"] = value.get("at")
    return stable


def _normal(value):
    return " ".join(value.split()) if isinstance(value, str) else value


def _owner_question(value):
    text = _normal(value) if isinstance(value, str) else value
    if isinstance(text, str) and text.casefold().rstrip(".") in {
            "no owner fact is required now", "no owner action is required now",
            "none", "nothing", "n/a"}:
        return ""
    return text


def _verified_completion(lifecycle, subject):
    if lifecycle.get("state") != "Completed":
        return False
    evidence = lifecycle.get("completion_evidence")
    if not isinstance(evidence, Mapping) or str(evidence.get("zone_id") or "") != subject:
        return False
    shutdown = evidence.get("shutdown_evidence")
    return (evidence.get("shutdown_verified") is True
            and (evidence.get("objective_satisfied") is True
                 or evidence.get("qualifies_as_completed_watering") is True)
            and isinstance(shutdown, Mapping)
            and shutdown.get("authoritative") is True
            and str(shutdown.get("state") or "").upper() == "OFF")


def owner_reason_material(value):
    """Preserve meaningful owner reason changes while collapsing backend tokens."""
    text = _normal(str(value or "")).strip()
    if (not text or text.casefold() in {
            "now_after_fresh_execution_revalidation", "zone_decision_not_run_now",
            "durable_zone_containment", "durable_parent_job_deferred"}
            or re.fullmatch(r"[a-z][a-z0-9]*(?:_[a-z0-9]+)+", text) is not None):
        return "canonical_decision_reason"
    return text.casefold().rstrip(".")[:300]
