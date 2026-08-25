"""Canonical, channel-neutral ROOTLINE B/C lifecycle projection.

This is a read-only projection over the existing recommendation, irrigation
history and execution evidence.  It creates no action, authority or queue.
"""
from __future__ import annotations

from typing import Any, Mapping


STATES = ("Recommended", "Revalidating", "Eligible", "Authorized",
          "Started", "Completed", "Held", "Failed")


def project_zone_lifecycle(*, zone_id: str, recommendation: Mapping[str, Any] | None,
                           history: Mapping[str, Any] | None = None,
                           execution: Mapping[str, Any] | None = None,
                           eligibility: Mapping[str, Any] | None = None) -> dict[str, Any]:
    recommendation = recommendation if isinstance(recommendation, Mapping) else {}
    history = history if isinstance(history, Mapping) else {}
    execution = execution if isinstance(execution, Mapping) else {}
    eligibility = eligibility if isinstance(eligibility, Mapping) else {}
    events = [row for row in history.get("events", ()) if isinstance(row, Mapping)]
    action = str(execution.get("action") or "")
    execution_state = str(execution.get("state") or "").casefold()
    decision = str(recommendation.get("status") or recommendation.get("recommendation") or "")

    revalidating = bool(history.get("incomplete_parent_job"))
    completed = _completed(events, execution,
                           allow_historical=not revalidating and not execution)
    failed = (action in {"contain_zone", "record_ambiguous_shutdown"}
              or execution_state in {"failed", "ambiguous", "contained"})
    started = (action == "mark_active" or execution_state in {"active", "started", "running"})
    authorized = action == "claim_before_on" or execution_state in {"claimed", "authorized"}
    eligible = eligibility.get("eligible") is True or execution.get("eligibility_id") is not None
    if failed:
        state, reason, next_action = "Failed", _reason(execution, recommendation), "ROOTLINE must reconcile and retry only the safe failed manager step."
    elif started:
        state, reason, next_action = "Started", _reason(execution, recommendation), "ROOTLINE must verify shutdown and the physical outcome."
    elif authorized:
        state, reason, next_action = "Authorized", _reason(execution, recommendation), "ROOTLINE must continue through the existing claimed execution."
    elif eligible:
        state, reason, next_action = "Eligible", _reason(eligibility, recommendation), "ROOTLINE must claim the existing canonical execution exactly once."
    elif completed:
        state, reason, next_action = "Completed", _completion_reason(completed), "Reassess at the next governed due time."
    elif revalidating:
        state, reason, next_action = "Revalidating", _reason(recommendation), "ROOTLINE must rebuild fresh eligibility for the remaining segment."
    elif decision.casefold() in {"recommend", "run", "proceed", "eligible"}:
        state, reason, next_action = "Recommended", _reason(recommendation), "ROOTLINE must revalidate current safety and standing authority."
    else:
        state, reason, next_action = "Held", _reason(recommendation), "ROOTLINE must reassess on the declared evidence or due-time trigger."

    result = {"contract_version": "rootline_zone_lifecycle.v1", "zone_id": zone_id,
            "state": state, "reason": reason or "Unknown",
            "next_action_owner": "ROOTLINE", "next_action": next_action,
            "supported_states": list(STATES)}
    if state == "Completed" and isinstance(completed, Mapping):
        result["completion_evidence"] = {
            "zone_id": zone_id,
            "shutdown_verified": completed.get("shutdown_verified") is True,
            "objective_satisfied": completed.get("objective_satisfied") is True,
            "qualifies_as_completed_watering": completed.get(
                "qualifies_as_completed_watering") is True,
            "shutdown_evidence": completed.get("shutdown_evidence") or
                completed.get("provider_final_off_evidence") or {},
        }
    return result


def _completed(events, execution, *, allow_historical):
    if (execution.get("action") == "record_completed"
            and execution.get("state") == "Completed"
            and execution.get("shutdown_verified") is True
            and execution.get("objective_satisfied") is True):
        return execution
    if not allow_historical:
        return None
    return next((row for row in reversed(events)
                 if row.get("qualifies_as_completed_watering") is True
                 and row.get("shutdown_verified") is True), None)


def validate_zone_lifecycle(value, *, zone_id):
    if (not isinstance(value, Mapping)
            or value.get("contract_version") != "rootline_zone_lifecycle.v1"
            or value.get("zone_id") != zone_id
            or value.get("state") not in STATES
            or value.get("next_action_owner") != "ROOTLINE"):
        return None
    return dict(value)


def _completion_reason(row):
    minutes = row.get("verified_runtime_minutes")
    return (f"Verified shutdown and {minutes} minutes of supported runtime are canonical."
            if minutes is not None else "Verified completion and shutdown are canonical.")


def _reason(*values):
    for value in values:
        if not isinstance(value, Mapping):
            continue
        for key in ("hold_reason", "eligibility_blocker", "reason", "transport_status", "status"):
            text = str(value.get(key) or "").strip()
            if text and text.casefold() not in {
                    "recommend", "run", "completed", "hold", "needs data", "do not run"}:
                return text
    return "Unknown"
