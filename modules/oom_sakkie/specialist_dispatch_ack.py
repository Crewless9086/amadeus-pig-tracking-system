"""Pure specialist dispatch acknowledgement and execution-truth contract.

The reducer performs no I/O.  It deliberately separates a control-plane
release from evidence that a named worker received, started, progressed, or
completed the released mission.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any, Iterable, Literal, Mapping, TypedDict


DispatchState = Literal[
    "release_requested",
    "released",
    "delivery_acknowledged",
    "started",
    "progress_observed",
    "completed",
    "contained",
    "ack_timeout",
]

EVENT_STATES = frozenset({
    "release_requested", "released", "delivery_acknowledged", "started",
    "progress_observed", "completed", "contained",
})
TERMINAL_STATES = frozenset({"completed", "contained"})
CONTRACT_VERSION = "oom_sakkie_specialist_dispatch_ack_v1"
SUCCESS_OUTCOMES = frozenset({"completed", "succeeded", "provider_confirmed"})
OPAQUE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,159}$")


class DispatchEvent(TypedDict, total=False):
    event_id: str
    state: DispatchState
    mission_id: str
    target_worker_id: str
    release_digest: str
    occurred_at: str
    acknowledgement_deadline_at: str
    start_deadline_at: str
    delivery_receipt_id: str
    heartbeat_at: str
    activity_observed_at: str
    activity_id: str
    outcome_artifact_id: str
    outcome_artifact_sha256: str
    outcome_status: str
    containment_reason: str


class DispatchContractError(ValueError):
    """Raised when durable evidence is malformed or internally contradictory."""


@dataclass(frozen=True)
class SystemicAlert:
    alert_id: str
    deduplication_key: str
    kind: Literal["specialist_dispatch_ack_timeout"]
    reason: Literal["delivery_acknowledgement_missing", "start_not_observed"]
    mission_id: str
    target_worker_id: str
    release_digest: str
    manual_coverage_required: bool
    automatic_resumption_claimed: bool = False
    buttons: int = 0
    calls_telegram: bool = False
    writes_performed: bool = False


@dataclass(frozen=True)
class DispatchSnapshot:
    version: str
    state: DispatchState
    mission_id: str
    target_worker_id: str
    release_digest: str
    release_requested: bool
    released: bool
    delivery_acknowledged: bool
    execution_started: bool
    progress_observed: bool
    completed: bool
    contained: bool
    outcome_artifact_id: str
    last_evidence_at: str
    ignored_event_ids: tuple[str, ...]
    alert: SystemicAlert | None
    automatic_resumption_claimed: bool = False
    calls_worker: bool = False
    calls_telegram: bool = False
    writes_performed: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def reconcile_specialist_dispatch(
    events: Iterable[Mapping[str, Any]],
    *,
    now: datetime | str,
    heartbeat_ttl_seconds: int = 300,
) -> DispatchSnapshot:
    """Reduce append-only dispatch evidence into one honest current state.

    Repeated identical event IDs are ignored.  Reusing an event ID with
    different content fails closed.  Evidence for another mission, release,
    or worker cannot advance this dispatch.
    """
    observed_now = _aware(now, "now")
    if heartbeat_ttl_seconds <= 0:
        raise DispatchContractError("heartbeat_ttl_seconds_must_be_positive")
    rows = _deduplicate(events)
    requests = [row for row in rows if row["state"] == "release_requested"]
    if not requests:
        raise DispatchContractError("release_requested_event_required")
    request = requests[0]
    binding = _binding(request)
    for other in requests[1:]:
        if _binding(other) != binding:
            raise DispatchContractError("conflicting_release_requests")

    related: list[dict[str, Any]] = []
    ignored: list[str] = []
    for row in rows:
        if _binding(row) == binding:
            related.append(row)
        else:
            ignored.append(row["event_id"])
    related.sort(key=lambda row: (_time(row, "occurred_at"), row["event_id"]))
    request_at = _time(request, "occurred_at")
    if request_at > observed_now:
        raise DispatchContractError("release_request_from_future")

    released_event = _first(related, "released")
    acknowledged_event = _first(related, "delivery_acknowledged")
    started_events = _all(related, "started")
    progress_events = _all(related, "progress_observed")
    completed_events = _all(related, "completed")
    contained_event = _first(related, "contained")

    released = released_event is not None
    acknowledged = False
    started_event = None
    progress_event = None
    completed_event = None

    ack_deadline = None
    start_deadline = None
    if released_event:
        release_at = _time(released_event, "occurred_at")
        ack_deadline = _time(released_event, "acknowledgement_deadline_at")
        start_deadline = _time(released_event, "start_deadline_at")
        if release_at < request_at:
            raise DispatchContractError("release_before_request")
        if release_at > observed_now:
            raise DispatchContractError("release_from_future")
        if ack_deadline > start_deadline:
            raise DispatchContractError("acknowledgement_deadline_after_start_deadline")
        if release_at > ack_deadline:
            raise DispatchContractError("release_after_acknowledgement_deadline")

    if released_event and acknowledged_event:
        receipt = _identity(acknowledged_event, "delivery_receipt_id")
        ack_at = _time(acknowledged_event, "occurred_at")
        acknowledged = bool(
            receipt and ack_at >= _time(released_event, "occurred_at")
            and ack_at <= ack_deadline and ack_at <= observed_now
        )

    if acknowledged:
        for candidate in started_events:
            activity_at = _valid_activity_time(candidate, observed_now, heartbeat_ttl_seconds)
            if activity_at is None:
                continue
            occurred = _time(candidate, "occurred_at")
            if occurred < _time(acknowledged_event, "occurred_at") or occurred > start_deadline:
                continue
            started_event = candidate
            break

    if started_event:
        for candidate in progress_events:
            activity_at = _valid_activity_time(candidate, observed_now, heartbeat_ttl_seconds)
            if activity_at is not None and _time(candidate, "occurred_at") >= _time(started_event, "occurred_at"):
                progress_event = candidate

    if started_event:
        for candidate in completed_events:
            completed_at = _time(candidate, "occurred_at")
            if completed_at < _time(started_event, "occurred_at") or completed_at > observed_now:
                continue
            if _valid_outcome_artifact(candidate):
                completed_event = candidate

    state: DispatchState = "release_requested"
    alert = None
    if released:
        state = "released"
    if acknowledged:
        state = "delivery_acknowledged"
    if started_event:
        state = "started"
    if progress_event:
        state = "progress_observed"
    valid_contained = None
    if contained_event:
        contained_at = _time(contained_event, "occurred_at")
        reason = str(contained_event.get("containment_reason") or "").strip()
        if request_at <= contained_at <= observed_now and 0 < len(reason) <= 240:
            valid_contained = contained_event
    terminal = []
    if completed_event:
        terminal.append((_time(completed_event, "occurred_at"), "completed"))
    if valid_contained:
        terminal.append((_time(valid_contained, "occurred_at"), "contained"))
    if len(terminal) == 2 and terminal[0][0] == terminal[1][0]:
        raise DispatchContractError("contradictory_terminal_events")
    if terminal:
        state = max(terminal)[1]  # type: ignore[assignment]
    elif released_event and not acknowledged and observed_now > ack_deadline:
        state = "ack_timeout"
        alert = _alert(binding, "delivery_acknowledgement_missing")
    elif acknowledged and not started_event and observed_now > start_deadline:
        state = "ack_timeout"
        alert = _alert(binding, "start_not_observed")

    last = max((_time(row, "occurred_at") for row in related), default=_time(request, "occurred_at"))
    return DispatchSnapshot(
        version=CONTRACT_VERSION,
        state=state,
        mission_id=binding[0],
        target_worker_id=binding[1],
        release_digest=binding[2],
        release_requested=True,
        released=released,
        delivery_acknowledged=acknowledged,
        execution_started=started_event is not None,
        progress_observed=progress_event is not None,
        completed=completed_event is not None,
        contained=state == "contained",
        outcome_artifact_id=(str(completed_event.get("outcome_artifact_id")) if state == "completed" and completed_event else ""),
        last_evidence_at=last.isoformat(),
        ignored_event_ids=tuple(sorted(ignored)),
        alert=alert,
    )


def _deduplicate(events: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    unique: dict[str, dict[str, Any]] = {}
    fingerprints: dict[str, str] = {}
    for raw in events:
        row = dict(raw) if isinstance(raw, Mapping) else {}
        event_id = _identity(row, "event_id")
        state = _required(row, "state")
        if state not in EVENT_STATES:
            raise DispatchContractError("unsupported_dispatch_state")
        _binding(row)
        _time(row, "occurred_at")
        fingerprint = hashlib.sha256(
            json.dumps(row, sort_keys=True, separators=(",", ":"), default=str).encode()
        ).hexdigest()
        if event_id in unique and fingerprints[event_id] != fingerprint:
            raise DispatchContractError("event_id_idempotency_conflict")
        unique[event_id] = row
        fingerprints[event_id] = fingerprint
    return list(unique.values())


def _binding(row: Mapping[str, Any]) -> tuple[str, str, str]:
    mission = _identity(row, "mission_id")
    worker = _identity(row, "target_worker_id")
    digest = _required(row, "release_digest").lower()
    if len(digest) != 64 or any(ch not in "0123456789abcdef" for ch in digest):
        raise DispatchContractError("release_digest_must_be_sha256")
    return mission, worker, digest


def _valid_activity_time(row: Mapping[str, Any], now: datetime, ttl: int) -> datetime | None:
    try:
        _identity(row, "activity_id")
    except DispatchContractError:
        return None
    occurred = _time(row, "occurred_at")
    heartbeat = _time(row, "heartbeat_at")
    observed = _time(row, "activity_observed_at")
    if occurred > now or heartbeat > observed or observed > occurred:
        return None
    age_at_observation = (observed - heartbeat).total_seconds()
    return heartbeat if age_at_observation <= ttl else None


def _valid_outcome_artifact(row: Mapping[str, Any]) -> bool:
    try:
        artifact_id = _identity(row, "outcome_artifact_id")
    except DispatchContractError:
        return False
    digest = str(row.get("outcome_artifact_sha256") or "").strip().lower()
    outcome = str(row.get("outcome_status") or "").strip().lower()
    return bool(
        artifact_id and outcome in SUCCESS_OUTCOMES
        and len(digest) == 64
        and all(ch in "0123456789abcdef" for ch in digest)
    )


def _alert(binding: tuple[str, str, str], reason: str) -> SystemicAlert:
    mission, worker, digest = binding
    key = "|".join((mission, worker, digest, reason))
    suffix = hashlib.sha256(key.encode()).hexdigest()[:24].upper()
    alert_id = f"OOMAQ-DISPATCH-ALERT-{suffix}"
    return SystemicAlert(
        alert_id=alert_id,
        deduplication_key=alert_id,
        kind="specialist_dispatch_ack_timeout",
        reason=reason,  # type: ignore[arg-type]
        mission_id=mission,
        target_worker_id=worker,
        release_digest=digest,
        manual_coverage_required=True,
    )


def _first(rows: list[dict[str, Any]], state: str) -> dict[str, Any] | None:
    return next((row for row in rows if row["state"] == state), None)


def _all(rows: list[dict[str, Any]], state: str) -> list[dict[str, Any]]:
    return [row for row in rows if row["state"] == state]


def _required(row: Mapping[str, Any], key: str) -> str:
    value = str(row.get(key) or "").strip()
    if not value:
        raise DispatchContractError(f"{key}_required")
    return value


def _identity(row: Mapping[str, Any], key: str) -> str:
    value = _required(row, key)
    if not OPAQUE_ID.fullmatch(value):
        raise DispatchContractError(f"{key}_invalid")
    return value


def _time(row_or_value: Mapping[str, Any] | datetime | str, key: str = "") -> datetime:
    value: Any = row_or_value.get(key) if isinstance(row_or_value, Mapping) else row_or_value
    return _aware(value, key or "timestamp")


def _aware(value: Any, field: str) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    else:
        try:
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except (TypeError, ValueError) as exc:
            raise DispatchContractError(f"{field}_must_be_iso_datetime") from exc
    if parsed.tzinfo is None:
        raise DispatchContractError(f"{field}_timezone_required")
    return parsed.astimezone(timezone.utc)
