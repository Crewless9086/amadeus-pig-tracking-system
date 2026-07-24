"""Pure, read-only lifecycle evidence reconciliation for Oom Sakkie.

The canary consumes already-read canonical evidence.  It cannot access a
database, dispatch an agent, change a pig record, or initiate a lifecycle or
commercial action.
"""

from __future__ import annotations


OWNER_AGENT = "oom-sakkie"
REQUIRED_AGENT = "herdmaster"
REQUIRED_SOURCES = {"pig_current_state", "pig_lifecycle_events"}
REQUIRED_EVENT_FIELDS = (
    "pig_id",
    "lifecycle_event_id",
    "lifecycle_event_type",
    "effective_at",
    "recorded_at",
    "actor_reference",
    "source_system",
    "source_reference",
    "idempotency_key",
)
FORBIDDEN_ACTIONS = (
    "farm_lifecycle_write",
    "pig_record_write",
    "customer_send",
    "payment",
    "reserve_stock",
    "commercial_action",
)


def reconcile_lifecycle_canary(*, observation: dict, evidence_by_agent: dict) -> dict:
    """Reconcile current pig state with immutable lifecycle-event evidence.

    Success means only that the supplied canonical evidence agrees.  It is an
    advisory check, not permission to perform a lifecycle action.
    """
    observation = observation if isinstance(observation, dict) else {}
    evidence_by_agent = evidence_by_agent if isinstance(evidence_by_agent, dict) else {}
    state, gaps = _observation_packet(observation)
    herdmaster, herdmaster_gaps = _herdmaster_packet(evidence_by_agent.get(REQUIRED_AGENT), state["pig_id"])
    gaps.extend(herdmaster_gaps)
    gaps.extend(_state_event_conflicts(state, herdmaster["lifecycle_events"]))
    unresolved_questions = _unique(gaps)
    verified = not unresolved_questions

    return {
        "success": verified,
        "status": "lifecycle_canary_verified" if verified else "lifecycle_reconciliation_required",
        "owner_agent": OWNER_AGENT,
        "mode": "production_read_only_advisory",
        "observation": state,
        "agent_evidence": {REQUIRED_AGENT: herdmaster},
        "agreement": {"reached": verified, "basis": "canonical lifecycle evidence agrees with current state" if verified else ""},
        "unresolved_questions": unresolved_questions,
        "authority": {
            "writes": False,
            "may_execute": False,
            "lifecycle_action": "none",
            "commercial_action": "none",
            "forbidden_actions": list(FORBIDDEN_ACTIONS),
        },
    }


def _observation_packet(observation):
    pig_id = str(observation.get("pig_id") or "").strip()
    observed_at = str(observation.get("observed_at") or "").strip()
    on_farm = observation.get("on_farm")
    gaps = []
    if not pig_id:
        gaps.append("Observation pig_id is required.")
    if not observed_at:
        gaps.append("Observation timestamp is required for freshness.")
    if not isinstance(on_farm, bool):
        gaps.append("Observation on_farm must be a boolean canonical current-state fact.")
    return {"pig_id": pig_id, "on_farm": on_farm, "observed_at": observed_at}, gaps


def _herdmaster_packet(evidence, observation_pig_id):
    evidence = evidence if isinstance(evidence, dict) else {}
    authority = str(evidence.get("authority") or "").strip()
    sources = evidence.get("sources") if isinstance(evidence.get("sources"), list) else []
    canonical_source_names = {
        str(row.get("name") or "").strip()
        for row in sources
        if isinstance(row, dict) and str(row.get("authority") or "").strip() == "canonical"
    }
    events = evidence.get("lifecycle_events") if isinstance(evidence.get("lifecycle_events"), list) else []
    gaps = []
    if authority != "read_only":
        gaps.append("Herdmaster evidence must declare read_only authority.")
    missing_sources = sorted(REQUIRED_SOURCES - canonical_source_names)
    if missing_sources:
        gaps.append("Herdmaster evidence must cite each source with canonical authority: " + ", ".join(missing_sources) + ".")
    if not events:
        gaps.append("Herdmaster evidence must include at least one lifecycle event.")

    seen_events = {}
    for index, event in enumerate(events):
        if not isinstance(event, dict):
            gaps.append(f"Lifecycle event {index} must be an evidence object.")
            continue
        for field in REQUIRED_EVENT_FIELDS:
            if not str(event.get(field) or "").strip():
                gaps.append(f"Lifecycle event {index} is missing {field}.")
        if observation_pig_id and str(event.get("pig_id") or "").strip() != observation_pig_id:
            gaps.append(f"Lifecycle event {index} pig_id must match observation pig_id.")
        event_id = str(event.get("lifecycle_event_id") or "").strip()
        if event_id:
            previous = seen_events.get(event_id)
            if previous is not None and previous != event:
                gaps.append(f"Lifecycle event {event_id} has duplicate conflicting evidence.")
            seen_events[event_id] = event
    return {
        "agent": REQUIRED_AGENT,
        "authority": authority,
        "sources": sources,
        "lifecycle_events": events,
    }, gaps


def _state_event_conflicts(state, events):
    if not isinstance(state.get("on_farm"), bool):
        return []
    effective_event = _effective_event(events)
    if not effective_event:
        return []
    event_type = str(effective_event.get("lifecycle_event_type") or "").strip()
    if event_type == "lifecycle_correction":
        return ["Effective lifecycle event is lifecycle_correction and does not state the corrected current lifecycle state."]
    if state["on_farm"] and event_type == "exited_farm":
        return ["Current state says on_farm=true but lifecycle evidence records exited_farm."]
    if not state["on_farm"] and event_type == "entered_farm":
        return ["Current state says on_farm=false but lifecycle evidence records entered_farm."]
    return []


def _effective_event(events):
    """Return the latest canonical event using the audit rail's ordering keys."""
    valid_events = [
        event for event in events
        if isinstance(event, dict)
        and str(event.get("effective_at") or "").strip()
        and str(event.get("recorded_at") or "").strip()
        and str(event.get("lifecycle_event_id") or "").strip()
    ]
    if not valid_events:
        return None
    return max(
        valid_events,
        key=lambda event: (
            str(event["effective_at"]),
            str(event["recorded_at"]),
            str(event["lifecycle_event_id"]),
        ),
    )


def _unique(items):
    return list(dict.fromkeys(items))
