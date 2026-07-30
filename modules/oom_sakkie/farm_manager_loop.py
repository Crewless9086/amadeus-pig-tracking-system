"""Pure, read-only contracts for Oom Sakkie's farm-manager coordination loop.

This module deliberately performs no reads, writes, network calls, dispatches, or
specialist reasoning. Callers supply structured specialist results; Oom Sakkie
only reconciles, prioritises, presents, and answers from that evidence.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from types import MappingProxyType
from typing import Any, Iterable, Mapping, Sequence


class WorkState(str, Enum):
    URGENT = "urgent"
    DUE_TODAY = "due_today"
    PLANNED = "planned"
    WAITING_EVIDENCE = "waiting_for_evidence"
    PROTECTED_OWNER_DECISION = "protected_owner_decision"
    COMPLETED = "completed"
    HANDLED = "handled"


class Authority(str, Enum):
    READ_ONLY = "read_only"
    ADVISORY = "advisory"
    OWNER_DECISION = "owner_decision"
    CUSTOMER_COMMITMENT = "customer_commitment"
    MONEY_ACTION = "money_action"
    FARM_WRITE = "farm_write"
    PUBLICATION = "publication"
    HARDWARE_COMMAND = "hardware_command"


class SpecialistAvailability(str, Enum):
    AVAILABLE = "available"
    STALE = "stale"
    DISABLED = "disabled"
    MISSING = "missing"
    CONTAINED = "contained"


PROTECTED_AUTHORITIES = frozenset(
    {
        Authority.OWNER_DECISION,
        Authority.CUSTOMER_COMMITMENT,
        Authority.MONEY_ACTION,
        Authority.FARM_WRITE,
        Authority.PUBLICATION,
        Authority.HARDWARE_COMMAND,
    }
)

FAMILY_MEMBERS = frozenset({"charl", "dad", "mom"})
ROOTLINE_SIGNAL_TYPES = frozenset(
    {"water_continuity", "forecast_rain", "solar_reserve", "grid_cost"}
)


@dataclass(frozen=True)
class Provenance:
    specialist: str
    result_id: str
    source_refs: tuple[str, ...]
    observed_at: datetime
    confidence: float

    def __post_init__(self) -> None:
        if not self.specialist.strip() or not self.result_id.strip():
            raise ValueError("specialist and result_id are required")
        if not self.source_refs:
            raise ValueError("structured source provenance is required")
        if any(not ref.strip() for ref in self.source_refs):
            raise ValueError("source provenance references cannot be blank")
        if self.observed_at.tzinfo is None:
            raise ValueError("observed_at must be timezone-aware")
        if not 0 <= self.confidence <= 1:
            raise ValueError("confidence must be between 0 and 1")


@dataclass(frozen=True)
class SpecialistWorkItem:
    item_id: str
    dedupe_key: str
    domain: str
    title: str
    why: str
    next_action: str
    assignee: str
    state: WorkState
    authority: Authority
    provenance: Provenance
    business_value: int = 0
    due_at: datetime | None = None
    stale_after_hours: int = 24
    genuine_question: str = ""
    question_for: str = ""
    media_usable: bool | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        required = (
            self.item_id,
            self.dedupe_key,
            self.domain,
            self.title,
            self.why,
            self.next_action,
            self.assignee,
        )
        if any(not str(value).strip() for value in required):
            raise ValueError("work item identity, meaning, action, and assignee are required")
        if self.assignee not in FAMILY_MEMBERS:
            raise ValueError("assignee must be charl, dad, or mom")
        if self.question_for and self.question_for not in FAMILY_MEMBERS:
            raise ValueError("question_for must be charl, dad, or mom")
        if self.business_value < 0:
            raise ValueError("business_value cannot be negative")
        if self.due_at is not None and self.due_at.tzinfo is None:
            raise ValueError("due_at must be timezone-aware")
        allowed_metadata = {
            "customer_or_exception": bool,
            "internal_housekeeping": bool,
            "requests_media": bool,
            "depends_on": tuple,
            "coordination_factors": tuple,
        }
        unknown = set(self.metadata) - set(allowed_metadata)
        if unknown:
            raise ValueError(f"unsupported coordination metadata: {sorted(unknown)}")
        for key, value in self.metadata.items():
            if not isinstance(value, allowed_metadata[key]):
                raise ValueError(f"{key} has the wrong coordination type")
        if self.metadata.get("customer_or_exception") and self.metadata.get(
            "internal_housekeeping"
        ):
            raise ValueError("work cannot be both customer-facing and housekeeping")
        for key in ("depends_on", "coordination_factors"):
            values = self.metadata.get(key, ())
            if any(not isinstance(value, str) or not value.strip() for value in values):
                raise ValueError(f"{key} must contain nonblank strings")
        object.__setattr__(self, "metadata", MappingProxyType(dict(self.metadata)))


@dataclass(frozen=True)
class SupportedAnswer:
    question_key: str
    answer: str
    provenance: Provenance


@dataclass(frozen=True)
class CoordinationSignal:
    signal_type: str
    value: str
    provenance: Provenance


@dataclass(frozen=True)
class SpecialistResult:
    specialist: str
    result_id: str
    observed_at: datetime
    availability: SpecialistAvailability = SpecialistAvailability.AVAILABLE
    work_items: tuple[SpecialistWorkItem, ...] = ()
    supported_answers: tuple[SupportedAnswer, ...] = ()
    coordination_signals: tuple[CoordinationSignal, ...] = ()
    resolved_dedupe_keys: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.specialist.strip() or not self.result_id.strip():
            raise ValueError("specialist result identity is required")
        if not isinstance(self.availability, SpecialistAvailability):
            raise ValueError("availability must use SpecialistAvailability")
        if self.observed_at.tzinfo is None:
            raise ValueError("observed_at must be timezone-aware")
        for item in self.work_items:
            if (
                item.provenance.specialist != self.specialist
                or item.provenance.result_id != self.result_id
            ):
                raise ValueError("work-item provenance must bind to its specialist result")
            if item.provenance.observed_at > self.observed_at:
                raise ValueError("work-item evidence cannot postdate its result")
        for answer in self.supported_answers:
            if (
                answer.provenance.specialist != self.specialist
                or answer.provenance.result_id != self.result_id
            ):
                raise ValueError("answer provenance must bind to its specialist result")
            if not answer.question_key.strip() or not answer.answer.strip():
                raise ValueError("supported answer key and text are required")
            if answer.provenance.observed_at > self.observed_at:
                raise ValueError("answer evidence cannot postdate its result")
        for signal in self.coordination_signals:
            if (
                signal.provenance.specialist != self.specialist
                or signal.provenance.result_id != self.result_id
            ):
                raise ValueError("coordination signal must bind to its specialist result")
            if not signal.signal_type.strip() or not signal.value.strip():
                raise ValueError("coordination signal type and value are required")
            if signal.provenance.observed_at > self.observed_at:
                raise ValueError("coordination signal cannot postdate its result")
            if self.specialist != "rootline" or signal.signal_type not in ROOTLINE_SIGNAL_TYPES:
                raise ValueError("coordination signal is not owned by this specialist")


@dataclass(frozen=True)
class FollowUp:
    follow_up_id: str
    dedupe_key: str
    promised_to: str
    status: str
    owner_specialist: str = ""
    evidence_result_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class FamilyBrief:
    generated_at: datetime
    queue: tuple[SpecialistWorkItem, ...]
    by_family_member: Mapping[str, tuple[SpecialistWorkItem, ...]]
    questions: Mapping[str, tuple[str, ...]]
    suppressed: Mapping[str, tuple[str, ...]]
    specialist_gaps: Mapping[str, str]
    follow_ups: tuple[FollowUp, ...]
    authority: str = "read_only_coordination"
    writes_performed: int = 0


_STATE_RANK = {
    WorkState.URGENT: 0,
    WorkState.DUE_TODAY: 1,
    WorkState.PLANNED: 2,
    WorkState.WAITING_EVIDENCE: 3,
    WorkState.PROTECTED_OWNER_DECISION: 4,
}

_DOMAIN_RANK = {
    "sales": 0,
    "herd": 1,
    "water_energy": 2,
    "marketing": 3,
}


def build_family_brief(
    results: Sequence[SpecialistResult],
    *,
    now: datetime | None = None,
    existing_follow_ups: Sequence[FollowUp] = (),
) -> FamilyBrief:
    """Reconcile structured results without invoking or mutating any system."""

    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    kept: dict[str, SpecialistWorkItem] = {}
    suppressed: dict[str, list[str]] = {
        "completed_or_handled": [],
        "stale_refreshed": [],
        "duplicate": [],
        "unusable_marketing_request": [],
        "lower_ranked": [],
    }
    specialist_gaps: dict[str, str] = {}
    accepted_results: list[SpecialistResult] = []

    for result in results:
        if result.observed_at > now:
            specialist_gaps[result.specialist] = "invalid_future_evidence"
            continue
        accepted_results.append(result)
        if result.availability in {
            SpecialistAvailability.DISABLED,
            SpecialistAvailability.MISSING,
            SpecialistAvailability.CONTAINED,
        }:
            specialist_gaps[result.specialist] = result.availability.value
            continue
        for item in result.work_items:
            _consider_item(item, result, now, kept, suppressed)

    queue = _reconcile_cross_domain(
        tuple(sorted(kept.values(), key=_priority_key)), accepted_results
    )
    selected: list[SpecialistWorkItem] = []
    counts = {member: 0 for member in FAMILY_MEMBERS}
    for item in queue:
        if counts[item.assignee] >= 3:
            suppressed["lower_ranked"].append(item.item_id)
            continue
        counts[item.assignee] += 1
        selected.append(item)
    queue = tuple(selected)
    by_member = MappingProxyType({
        member: tuple(item for item in queue if item.assignee == member)
        for member in ("charl", "dad", "mom")
    })
    questions = _minimal_questions(queue)
    follow_ups = _reassess_follow_ups(existing_follow_ups, accepted_results, queue)
    return FamilyBrief(
        generated_at=now,
        queue=queue,
        by_family_member=by_member,
        questions=questions,
        suppressed=MappingProxyType(
            {key: tuple(sorted(value)) for key, value in suppressed.items()}
        ),
        specialist_gaps=MappingProxyType(dict(sorted(specialist_gaps.items()))),
        follow_ups=follow_ups,
    )


def _consider_item(item, result, now, kept, suppressed):
    if item.state in {WorkState.COMPLETED, WorkState.HANDLED}:
        suppressed["completed_or_handled"].append(item.item_id)
        return
    if result.availability is SpecialistAvailability.STALE:
        item = _as_evidence_refresh(item)
        suppressed["stale_refreshed"].append(item.item_id)
    if item.provenance.observed_at > now:
        raise ValueError("future-dated specialist evidence is not accepted")
    if result.availability is not SpecialistAvailability.STALE and _is_stale(item, now):
        item = _as_evidence_refresh(item)
        suppressed["stale_refreshed"].append(item.item_id)
    if (
        item.domain == "marketing"
        and item.metadata.get("requests_media")
        and item.media_usable is not True
    ):
        suppressed["unusable_marketing_request"].append(item.item_id)
        return
    prior = kept.get(item.dedupe_key)
    if prior is None:
        kept[item.dedupe_key] = item
        return
    winner, loser = _prefer(prior, item)
    kept[item.dedupe_key] = winner
    suppressed["duplicate"].append(loser.item_id)


def answer_supported_question(
    question_key: str,
    results: Sequence[SpecialistResult],
    *,
    now: datetime | None = None,
) -> Mapping[str, Any]:
    """Return a conversational answer only when structured evidence supports it."""

    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    candidates = [
        answer
        for result in results
        if result.availability is SpecialistAvailability.AVAILABLE
        for answer in result.supported_answers
        if answer.question_key == question_key
        and result.observed_at <= now
        and answer.provenance.observed_at <= now
    ]
    if not candidates:
        return {
            "status": "needs_evidence",
            "answer": "",
            "question": "Which exact farm fact should the relevant specialist verify?",
            "writes_performed": 0,
        }
    selected = max(
        candidates,
        key=lambda answer: (
            answer.provenance.observed_at,
            answer.provenance.confidence,
            answer.provenance.specialist,
            answer.provenance.result_id,
            answer.answer,
        ),
    )
    return {
        "status": "supported",
        "answer": selected.answer,
        "provenance": {
            "specialist": selected.provenance.specialist,
            "result_id": selected.provenance.result_id,
            "source_count": len(selected.provenance.source_refs),
            "observed_at": selected.provenance.observed_at.isoformat(),
            "confidence": selected.provenance.confidence,
        },
        "writes_performed": 0,
    }


def render_family_brief(brief: FamilyBrief, member: str) -> str:
    """Present only a family member's relevant actions and smallest question."""

    if member not in FAMILY_MEMBERS:
        raise ValueError("unknown family member")
    lines = [f"{member.title()}, here is what matters now:"]
    for item in brief.by_family_member[member]:
        protected = item.authority in PROTECTED_AUTHORITIES
        action = (
            "Charl must review the specialist proposal and explicitly approve "
            "it through its governed domain rail"
            if protected
            else item.next_action
        )
        boundary = " Nothing has been executed." if protected else ""
        lines.append(
            f"- [{item.state.value}] {item.title}: {item.why} "
            f"Next: {action}.{boundary} "
            f"(Source: {item.provenance.specialist}/{item.provenance.result_id})"
        )
    if not brief.by_family_member[member]:
        lines.append("- No current action is assigned to you.")
    for question in brief.questions[member]:
        lines.append(f"Question: {question}")
    return "\n".join(lines)


def render_consolidated_brief(brief: FamilyBrief) -> str:
    """Render one operational brief while retaining family-specific sections."""

    sections = ["OOM SAKKIE FAMILY BRIEF", "What matters, in farm order:"]
    for item in brief.queue:
        protected = item.authority in PROTECTED_AUTHORITIES
        action = (
            "Charl reviews and explicitly decides through the specialist's governed rail"
            if protected
            else item.next_action
        )
        sections.append(
            f"- {item.title} ({item.assignee}, {item.state.value}): {item.why} "
            f"Next: {action}. [{item.provenance.specialist}/{item.provenance.result_id}]"
        )
    selected_question = next(
        (
            (member, brief.questions[member][0])
            for member in ("charl", "dad", "mom")
            if brief.questions[member]
        ),
        None,
    )
    if selected_question:
        member, question = selected_question
        sections.extend(("", f"One family question for {member.title()}: {question}"))
    return "\n".join(sections).strip()


def _all_items(results: Iterable[SpecialistResult]) -> Iterable[SpecialistWorkItem]:
    for result in results:
        if result.availability in {
            SpecialistAvailability.DISABLED,
            SpecialistAvailability.MISSING,
            SpecialistAvailability.CONTAINED,
        }:
            continue
        yield from result.work_items


def _is_stale(item: SpecialistWorkItem, now: datetime) -> bool:
    if item.stale_after_hours <= 0:
        return False
    age_hours = (now - item.provenance.observed_at).total_seconds() / 3600
    return age_hours > item.stale_after_hours


def _prefer(
    left: SpecialistWorkItem, right: SpecialistWorkItem
) -> tuple[SpecialistWorkItem, SpecialistWorkItem]:
    return (left, right) if _priority_key(left) <= _priority_key(right) else (right, left)


def _priority_key(item: SpecialistWorkItem) -> tuple[Any, ...]:
    customer_or_exception = 0 if item.metadata.get("customer_or_exception") else 1
    internal_housekeeping = 1 if item.metadata.get("internal_housekeeping") else 0
    return (
        customer_or_exception,
        internal_housekeeping,
        _STATE_RANK[item.state],
        -item.business_value,
        _DOMAIN_RANK.get(item.domain, 9),
        item.due_at or datetime.max.replace(tzinfo=timezone.utc),
        item.item_id,
        -item.provenance.observed_at.timestamp(),
        item.provenance.specialist,
        item.provenance.result_id,
        item.title,
        item.next_action,
    )


def _minimal_questions(
    queue: Sequence[SpecialistWorkItem],
) -> Mapping[str, tuple[str, ...]]:
    candidates = [
        item
        for item in queue
        if item.question_for in FAMILY_MEMBERS
        and item.genuine_question.strip()
        and item.state is WorkState.WAITING_EVIDENCE
    ]
    selected = min(candidates, key=_priority_key) if candidates else None
    return MappingProxyType({
        member: (
            (selected.genuine_question,)
            if selected is not None and selected.question_for == member
            else ()
        )
        for member in ("charl", "dad", "mom")
    })


def _reassess_follow_ups(
    existing: Sequence[FollowUp],
    results: Sequence[SpecialistResult],
    queue: Sequence[SpecialistWorkItem],
) -> tuple[FollowUp, ...]:
    current_keys = {item.dedupe_key for item in queue}
    evidence_by_key: dict[str, list[str]] = {}
    resolution_by_key: dict[str, list[str]] = {}
    for result in results:
        if result.availability is not SpecialistAvailability.AVAILABLE:
            continue
        for key in result.resolved_dedupe_keys:
            resolution_by_key.setdefault(key, []).append(
                f"{result.specialist}:{result.result_id}"
            )
    for item in _all_items(results):
        evidence_by_key.setdefault(item.dedupe_key, []).append(
            f"{item.provenance.specialist}:{item.provenance.result_id}"
        )
    output = []
    for follow_up in existing:
        evidence = tuple(sorted(set(evidence_by_key.get(follow_up.dedupe_key, ()))))
        resolution = tuple(
            value
            for value in sorted(set(resolution_by_key.get(follow_up.dedupe_key, ())))
            if follow_up.owner_specialist
            and value.startswith(f"{follow_up.owner_specialist}:")
        )
        if resolution:
            status = "closed_by_explicit_resolution"
            evidence = resolution
        elif evidence and follow_up.dedupe_key in current_keys:
            status = "reassessed_open"
        else:
            status = follow_up.status
        output.append(
            FollowUp(
                follow_up_id=follow_up.follow_up_id,
                dedupe_key=follow_up.dedupe_key,
                promised_to=follow_up.promised_to,
                status=status,
                owner_specialist=follow_up.owner_specialist,
                evidence_result_ids=evidence or follow_up.evidence_result_ids,
            )
        )
    return tuple(output)


def _as_evidence_refresh(item: SpecialistWorkItem) -> SpecialistWorkItem:
    return SpecialistWorkItem(
        **{
            **item.__dict__,
            "state": WorkState.WAITING_EVIDENCE,
            "why": f"{item.why}; the specialist evidence is now stale",
            "next_action": f"refresh {item.provenance.specialist} evidence before acting",
        }
    )


def _reconcile_cross_domain(
    queue: tuple[SpecialistWorkItem, ...],
    results: Sequence[SpecialistResult],
) -> tuple[SpecialistWorkItem, ...]:
    """Apply coordination dependencies without replacing specialist reasoning."""

    reconciled = list(queue)
    while True:
        ready_keys = {
            item.dedupe_key
            for item in reconciled
            if item.state is not WorkState.WAITING_EVIDENCE
        }
        changed = False
        next_items = []
        for item in reconciled:
            missing = tuple(
                key
                for key in item.metadata.get("depends_on", ())
                if key not in ready_keys
            )
            if missing and item.state is not WorkState.WAITING_EVIDENCE:
                item = SpecialistWorkItem(
                    **{
                        **item.__dict__,
                        "state": WorkState.WAITING_EVIDENCE,
                        "why": (
                            f"{item.why}; coordination is waiting for "
                            f"{', '.join(missing)}"
                        ),
                        "next_action": (
                            "obtain the missing specialist result before proceeding"
                        ),
                    }
                )
                changed = True
            next_items.append(item)
        reconciled = next_items
        if not changed:
            break
    reconciled = [_balance_water_energy(item, results) for item in reconciled]
    return tuple(sorted(reconciled, key=_priority_key))


def _balance_water_energy(
    item: SpecialistWorkItem, results: Sequence[SpecialistResult]
) -> SpecialistWorkItem:
    if item.domain != "water_energy" or item.state is WorkState.WAITING_EVIDENCE:
        return item
    required = {"water_continuity", "forecast_rain", "solar_reserve", "grid_cost"}
    complete_results = []
    for result in results:
        if (
            result.availability is SpecialistAvailability.AVAILABLE
            and result.specialist == "rootline"
        ):
            signal_map = {
                signal.signal_type: signal for signal in result.coordination_signals
            }
            if required.issubset(signal_map):
                complete_results.append((result, signal_map))
    if not complete_results:
        return item
    _, signals = max(
        complete_results,
        key=lambda pair: (pair[0].observed_at, pair[0].result_id),
    )
    values = {key: signals[key].value for key in required}
    if (
        values["water_continuity"] == "needs_water"
        and values["forecast_rain"] == "none_material"
        and values["solar_reserve"] == "sufficient"
        and values["grid_cost"] == "peak"
    ):
        return SpecialistWorkItem(
            **{
                **item.__dict__,
                "why": (
                    f"{item.why}; water is needed, material rain is not forecast, "
                    "solar reserve is sufficient, and grid cost is at peak"
                ),
                "next_action": (
                    "prioritise the owner-reviewed water plan in the safe solar "
                    "window and avoid the grid-cost peak"
                ),
            }
        )
    return item
