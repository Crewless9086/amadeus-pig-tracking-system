"""Canonical, channel-neutral ROOTLINE B/C lifecycle projection.

This is a read-only projection over the existing recommendation, irrigation
history and execution evidence.  It creates no action, authority or queue.
"""
from __future__ import annotations

from datetime import datetime, timezone
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
    # History owns the complete per-run projection. The selected display row
    # remains raw; it must not overwrite reconciled same-run context.
    if "execution_exceptions" in history:
        exceptions = history.get("execution_exceptions")
        exceptions = exceptions if isinstance(exceptions, (list, tuple)) else ()
        result["execution_exceptions"] = validated_shutdown_exceptions(
            {"execution_exceptions": exceptions}, zone_id=zone_id)
    else:
        result["execution_exceptions"] = project_execution_shutdown_exceptions(
            [execution], evidence_cutoff=evidence_cutoff)
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
    """Return an attributable read time, never an inferred switching time."""
    evidence = execution.get(key) if isinstance(execution, Mapping) else None
    if (not isinstance(evidence, Mapping) or evidence.get("authoritative") is not True
            or str(evidence.get("state") or "").upper() != state):
        return None
    for field in ("execution_id", "zone_id", "device_id", "channel"):
        if field in evidence and str(evidence[field]) != str(execution.get(field)):
            return None
    retrieved = _aware_timestamp(evidence.get("retrieved_at"))
    observed = _aware_timestamp(evidence.get("observed_at"))
    if "retrieved_at" in evidence and "observed_at" in evidence:
        return retrieved if retrieved is not None and retrieved == observed else None
    return retrieved if "retrieved_at" in evidence else observed


def project_execution_shutdown_exceptions(rows, *, evidence_cutoff=None, canonical_ordered=False):
    """Preserve shutdown uncertainty for one exact run, independent of row order.

    Context can be absent on sparse later events, but conflicting original
    context is never replaced. A flag and OFF readback must share one terminal
    row; neither another execution nor merging two rows can provide that proof.
    """
    rows = [row for row in rows if isinstance(row, Mapping)]
    identities = {(str(row.get("zone_id") or "").strip(),
                   str(row.get("execution_id") or "").strip()) for row in rows}
    if len(identities) != 1:
        return []
    zone, identity = next(iter(identities))
    if zone not in {"B12345", "C12345"} or not identity:
        return []
    terminal_actions = {"record_completed", "record_claim_recovery", "record_ambiguous_shutdown"}
    failed_actions = {"contain_zone", "record_ambiguous_shutdown"}
    involved = any(str(row.get("action") or "") in terminal_actions | failed_actions | {"mark_active", "claim_before_on"}
        or str(row.get("state") or "").casefold() in {
            "active", "started", "running", "completed", "failed", "ambiguous", "contained", "claimed", "claimed_recovery_required"}
        for row in rows)
    if not involved:
        return []
    cutoff = _aware_timestamp(evidence_cutoff)
    cutoff_invalid = evidence_cutoff is not None and cutoff is None
    primary, primary_invalid = _consistent_time(rows, "primary_stop_deadline")
    native, native_invalid = _consistent_time(rows, "native_fail_stop_deadline")
    deadline = min((value for value in (primary, native) if value is not None), default=None)
    deadline_invalid = primary_invalid or native_invalid or primary is None or native is None or primary > native
    claimed, claimed_invalid = _consistent_time(rows, "claimed_at")
    starts = [controller_readback_time(row, "start_evidence", "ON")
              for row in rows if "start_evidence" in row]
    start_invalid = claimed_invalid or any(value is None for value in starts)
    starts = {value for value in starts if value is not None}
    start_invalid = start_invalid or len(starts) > 1
    lower_bound = max([value for value in (claimed, *starts) if value is not None], default=None)
    verified_times, malformed_terminal = set(), False
    verified_orders = set()
    evidence_identities = {}
    for order, row in enumerate(rows):
        if str(row.get("action") or "") not in terminal_actions:
            continue
        stopped = controller_readback_time(row, "shutdown_evidence", "OFF")
        valid = (row.get("shutdown_verified") is True and stopped is not None
            and lower_bound is not None and not start_invalid and not cutoff_invalid
            and cutoff is not None and lower_bound <= stopped <= cutoff)
        if valid:
            verified_times.add(stopped)
            verified_orders.add(order)
        # An explicitly asserted but invalid proof must not be repaired by
        # borrowing another terminal row's timestamp or boolean.
        if row.get("shutdown_verified") is True and not valid:
            malformed_terminal = True
        evidence = row.get("shutdown_evidence")
        if isinstance(evidence, Mapping) and evidence.get("evidence_id"):
            key = str(evidence["evidence_id"])
            evidence_identities.setdefault(key, set()).add((
                stopped, evidence.get("authoritative") is True,
                str(evidence.get("state") or "")))
    conflicting_proof = any(len(values) > 1 for values in evidence_identities.values())
    verified = bool(verified_times) and not malformed_terminal and not conflicting_proof
    stopped = max(verified_times, default=None)
    # A later unresolved terminal/containment cannot be hidden by earlier OFF.
    # Untimed rows need the production SELECT's canonical append ordering;
    # callers supplying an unordered history cannot infer that resolution.
    if verified:
        for order, row in enumerate(rows):
            if (str(row.get("action") or "") not in failed_actions | terminal_actions
                    or order in verified_orders):
                continue
            evidence = row.get("shutdown_evidence")
            observed = (_aware_timestamp(evidence.get("retrieved_at") or evidence.get("observed_at"))
                        if isinstance(evidence, Mapping) else None)
            if ((observed is not None and observed >= stopped)
                    or (canonical_ordered and order > max(verified_orders))
                    or (not canonical_ordered and observed is None)):
                verified = False
    def exception(kind, proof=None):
        return {"execution_id": identity, "zone_id": zone, "kind": kind,
            "stop_deadline": deadline.isoformat() if deadline else None,
            "controller_off_verified": proof is not None,
            "controller_off_at": proof.isoformat() if proof else None}
    result = []
    if deadline_invalid:
        result.append(exception("shutdown_deadline_unavailable", stopped if verified else None))
    elif not verified and (any(str(row.get("action") or "") in terminal_actions | failed_actions for row in rows)
            or (cutoff is not None and cutoff >= deadline)):
        result.append(exception("shutdown_unverified"))
    # Keep the first late attributable read even if a later event presents an
    # earlier-looking OFF. This records a discrepancy, not a watering duration.
    late = min((value for value in verified_times if deadline and value > deadline), default=None)
    if late is not None:
        result.append(exception("off_readback_after_deadline", late))
    return result


def validated_shutdown_exceptions(lifecycle, *, zone_id):
    """Stable, bounded-shape exception material for existing owner surfaces."""
    if not isinstance(lifecycle, Mapping):
        return []
    rows = lifecycle.get("execution_exceptions")
    if not isinstance(rows, (list, tuple)):
        return []
    unique = {}
    for row in rows:
        if not isinstance(row, Mapping) or row.get("zone_id") != zone_id:
            continue
        identity, kind = row.get("execution_id"), row.get("kind")
        if not isinstance(identity, str) or not identity.strip() or not isinstance(kind, str):
            continue
        if kind not in {"shutdown_unverified", "shutdown_deadline_unavailable", "off_readback_after_deadline"}:
            continue
        verified = row.get("controller_off_verified")
        if not isinstance(verified, bool):
            continue
        deadline = _aware_timestamp(row.get("stop_deadline"))
        stopped = _aware_timestamp(row.get("controller_off_at"))
        if row.get("stop_deadline") is not None and deadline is None:
            continue
        if verified != (stopped is not None):
            continue
        if not verified and row.get("controller_off_at") is not None:
            continue
        if kind == "shutdown_unverified" and (verified or deadline is None):
            continue
        if kind == "off_readback_after_deadline" and (not verified or deadline is None or stopped <= deadline):
            continue
        item = {"execution_id": identity.strip(), "zone_id": zone_id, "kind": kind,
            "stop_deadline": deadline.isoformat() if deadline else None,
            "controller_off_verified": verified,
            "controller_off_at": stopped.isoformat() if stopped else None}
        unique[tuple(str(item[key]) for key in item)] = item
    return [unique[key] for key in sorted(unique)]


def _consistent_time(rows, key):
    supplied = [_aware_timestamp(row.get(key)) for row in rows if key in row]
    values = {value for value in supplied if value is not None}
    return (next(iter(values)) if len(values) == 1 else None,
            any(value is None for value in supplied) or len(values) > 1)


def _aware_timestamp(value):
    try:
        parsed = value if isinstance(value, datetime) else datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed.astimezone(timezone.utc) if parsed.tzinfo is not None and parsed.utcoffset() is not None else None
    except (TypeError, ValueError, OverflowError):
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
