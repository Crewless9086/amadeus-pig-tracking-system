"""Canonical, channel-neutral ROOTLINE B/C lifecycle projection.

This is a read-only projection over the existing recommendation, irrigation
history and execution evidence.  It creates no action, authority or queue.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Mapping


STATES = ("Recommended", "Revalidating", "Eligible", "Authorized",
          "Started", "Completed", "Held", "Failed")


def project_zone_lifecycle(*, zone_id: str, recommendation: Mapping[str, Any] | None,
                           history: Mapping[str, Any] | None = None,
                           execution: Mapping[str, Any] | None = None,
                           eligibility: Mapping[str, Any] | None = None,
                           evidence_cutoff=None) -> dict[str, Any]:
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
    terminal = action == "record_completed" or execution_state == "completed"
    eligible = (not terminal and
        (eligibility.get("eligible") is True or bool(execution.get("eligibility_id"))))
    if failed:
        state, reason, next_action = "Failed", _reason(execution, recommendation), "ROOTLINE must reconcile and retry only the safe failed manager step."
    elif started:
        state, reason, next_action = "Started", _reason(execution, recommendation), "ROOTLINE must verify shutdown and the physical outcome."
    elif authorized:
        state, reason, next_action = "Authorized", _reason(execution, recommendation), "ROOTLINE must continue through the existing claimed execution."
    elif revalidating and terminal:
        state, reason, next_action = "Revalidating", _reason(recommendation), "ROOTLINE must rebuild fresh eligibility for the remaining segment."
    elif completed:
        state, reason, next_action = "Completed", _completion_reason(completed), "Reassess at the next governed due time."
    elif eligible:
        state, reason, next_action = "Eligible", _reason(eligibility, recommendation), "ROOTLINE must claim the existing canonical execution exactly once."
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
    exceptions = [dict(row) for row in history.get("execution_exceptions", ())
                  if isinstance(row, Mapping) and row.get("zone_id") == zone_id]
    current_exception = project_shutdown_exception(execution, evidence_cutoff=evidence_cutoff)
    if current_exception and current_exception["zone_id"] == zone_id:
        key = (current_exception["execution_id"], current_exception["kind"])
        if current_exception["kind"] != "off_readback_after_deadline":
            exceptions = [row for row in exceptions
                          if (row.get("execution_id"), row.get("kind")) != key]
        if not any((row.get("execution_id"), row.get("kind")) == key for row in exceptions):
            exceptions.append(current_exception)
    result["execution_exceptions"] = sorted(exceptions, key=lambda row: (row["execution_id"], row["kind"]))
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


def controller_readback_time(execution, key, state):
    """Time the controller was read, never an inferred physical transition."""
    evidence = execution.get(key) if isinstance(execution, Mapping) else None
    if (not isinstance(evidence, Mapping) or evidence.get("authoritative") is not True
            or str(evidence.get("state") or "").upper() != state):
        return None
    # The live transport supplies retrieved_at. observed_at is the retained
    # timestamped-readback shape, not permission to invent a switching time.
    retrieved = _aware_timestamp(evidence.get("retrieved_at"))
    observed = _aware_timestamp(evidence.get("observed_at"))
    if evidence.get("retrieved_at") and evidence.get("observed_at"):
        return retrieved if retrieved is not None and retrieved == observed else None
    return retrieved if evidence.get("retrieved_at") else observed


def project_shutdown_exception(execution, *, evidence_cutoff=None, terminal_record_required=True):
    """Derive stable exception facts solely from one canonical execution."""
    if not isinstance(execution, Mapping):
        return None
    identity = str(execution.get("execution_id") or "").strip()
    zone = str(execution.get("zone_id") or "").strip()
    if not identity or zone not in {"B12345", "C12345"}:
        return None
    action, state = str(execution.get("action") or ""), str(execution.get("state") or "").casefold()
    failed = (action in {"contain_zone", "record_ambiguous_shutdown"}
              or state in {"failed", "ambiguous", "contained"})
    involved = (failed or action in {"mark_active", "record_completed", "record_claim_recovery"}
                or state in {"active", "started", "running", "completed"})
    if not involved:
        return None
    cutoff = _aware_timestamp(evidence_cutoff)
    primary = _aware_timestamp(execution.get("primary_stop_deadline"))
    native = _aware_timestamp(execution.get("native_fail_stop_deadline"))
    deadline = min((value for value in (primary, native) if value is not None), default=None)
    stopped = controller_readback_time(execution, "shutdown_evidence", "OFF")
    verified = ((action in {"record_completed", "record_claim_recovery"}
                 or (not terminal_record_required and state == "completed"))
                and execution.get("shutdown_verified") is True and stopped is not None
                and (cutoff is None or stopped <= cutoff))
    if primary is None or native is None or primary > native:
        kind = "shutdown_deadline_unavailable"
    elif verified and stopped > deadline:
        kind = "off_readback_after_deadline"
    elif not verified and (failed or action in {"record_completed", "record_claim_recovery"}
                           or (cutoff is not None and deadline is not None and cutoff >= deadline)):
        kind = "shutdown_unverified"
    else:
        return None
    return {"execution_id": identity, "zone_id": zone, "kind": kind,
            "stop_deadline": deadline.isoformat() if deadline else None,
            "controller_off_verified": verified,
            "controller_off_at": stopped.isoformat() if verified else None}


def _aware_timestamp(value):
    try:
        parsed = value if isinstance(value, datetime) else datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed if parsed.tzinfo is not None else None
    except (TypeError, ValueError):
        return None


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
