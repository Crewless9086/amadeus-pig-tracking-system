"""Pure, read-only contracts for Oom Sakkie's farm-manager coordination loop.

This module deliberately performs no reads, writes, network calls, dispatches, or
specialist reasoning. Callers supply structured specialist results; Oom Sakkie
only reconciles, prioritises, presents, and answers from that evidence.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from enum import Enum
import math
import re
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
            "mortality_fingerprints": dict,
            "welfare_exception": bool,
            "mortality_packet": dict,
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


@dataclass(frozen=True)
class CustomerDemandEvidence:
    demand_id: str
    family_label: str
    quantity: int
    sex: str
    minimum_weight_kg: float
    maximum_weight_kg: float
    needed_by: datetime
    commercial_value_score: int
    provenance: Provenance
    completed: bool = False

    def __post_init__(self) -> None:
        if self.provenance.specialist != "sam_livestock":
            raise ValueError("customer demand must be owned by SAM Livestock")
        if not self.demand_id.strip() or self.quantity <= 0:
            raise ValueError("demand identity and positive quantity are required")
        if not re.fullmatch(r"Opportunity [A-Z][A-Z0-9]{0,7}", self.family_label):
            raise ValueError("family-safe demand label is required")
        if self.sex not in {"male", "female", "either"}:
            raise ValueError("demand sex must be male, female, or either")
        if not 0 < self.minimum_weight_kg <= self.maximum_weight_kg:
            raise ValueError("demand weight range is invalid")
        if self.needed_by.tzinfo is None:
            raise ValueError("needed_by must be timezone-aware")
        if not 0 <= self.commercial_value_score <= 100:
            raise ValueError("commercial value score must be between 0 and 100")


@dataclass(frozen=True)
class SaleInventoryEvidence:
    animal_ref: str
    family_label: str
    sex: str
    current_weight_kg: float | None
    weight_observed_at: datetime | None
    sale_eligible_without_weight: bool
    status: str
    compatible_demand_ids: tuple[str, ...]
    provenance: Provenance
    completed: bool = False

    def __post_init__(self) -> None:
        if self.provenance.specialist != "herdmaster":
            raise ValueError("sale inventory must be owned by HERDMASTER")
        if not self.animal_ref.strip():
            raise ValueError("opaque animal_ref is required")
        if not re.fullmatch(r"Animal [A-Z][A-Z0-9]{0,7}", self.family_label):
            raise ValueError("family-safe animal label is required")
        if self.sex not in {"male", "female", "unknown"}:
            raise ValueError("inventory sex is invalid")
        if self.status not in {"usable_now", "needs_fresh_weight", "blocked"}:
            raise ValueError("inventory status is invalid")
        if self.weight_observed_at is not None and self.weight_observed_at.tzinfo is None:
            raise ValueError("weight_observed_at must be timezone-aware")
        if self.status == "usable_now" and (
            self.current_weight_kg is None or self.weight_observed_at is None
        ):
            raise ValueError("usable_now requires a measured weight and observation time")
        if self.current_weight_kg is not None and (
            not math.isfinite(self.current_weight_kg) or self.current_weight_kg <= 0
        ):
            raise ValueError("measured weight must be positive and finite")
        if (
            self.weight_observed_at is not None
            and self.weight_observed_at > self.provenance.observed_at
        ):
            raise ValueError("weight observation cannot postdate inventory evidence")
        if any(not demand_id.strip() for demand_id in self.compatible_demand_ids):
            raise ValueError("compatible demand IDs cannot be blank")
        object.__setattr__(
            self,
            "compatible_demand_ids",
            tuple(sorted(set(self.compatible_demand_ids))),
        )


@dataclass(frozen=True)
class SalesWeighingPacket:
    status: str
    usable_inventory_now: tuple[Mapping[str, Any], ...]
    weigh_next: tuple[Mapping[str, Any], ...]
    customer_opportunity_unlocked: tuple[Mapping[str, Any], ...]
    protected_decisions: tuple[str, ...]
    family_actions: Mapping[str, tuple[str, ...]]
    family_question: str
    automatic_follow_up_instruction: Mapping[str, Any]
    evidence_gaps: tuple[str, ...]
    writes_performed: int = 0


@dataclass(frozen=True)
class HerdmasterInventoryProjection:
    projection_id: str
    contract_version: str
    source_revision: str
    source_sha256: str
    observed_at: datetime
    weight_date: date
    weight_age_days: int
    weight_observation_time_status: str
    canonical_rows_evaluated: int
    sale_eligible_count: int
    price_provenanced_count: int
    weight_only_blocked_count: int
    selected_reweigh_count: int
    withdrawal_unknown_excluded_count: int
    withdrawal_unknown_exclusion_affirmed: bool
    field_list_delivery_status: str
    field_list_receipt_id: str
    field_list_receipt_sha256: str
    field_list_message_sha256: str
    field_list_send_attempts: int
    provenance: Provenance

    def __post_init__(self) -> None:
        if self.provenance.specialist != "herdmaster":
            raise ValueError("inventory projection must be HERDMASTER-owned")
        if self.provenance.result_id != self.projection_id:
            raise ValueError("inventory projection provenance is mismatched")
        if not re.fullmatch(r"[0-9a-f]{40}", self.source_revision):
            raise ValueError("exact lowercase source revision is required")
        if not re.fullmatch(r"[0-9A-F]{64}", self.source_sha256):
            raise ValueError("uppercase source SHA-256 is required")
        if self.observed_at.tzinfo is None:
            raise ValueError("projection observed_at must be timezone-aware")
        if self.provenance.observed_at > self.observed_at:
            raise ValueError("projection provenance cannot postdate its envelope")
        counts = (
            self.canonical_rows_evaluated,
            self.sale_eligible_count,
            self.price_provenanced_count,
            self.weight_only_blocked_count,
            self.selected_reweigh_count,
            self.withdrawal_unknown_excluded_count,
        )
        if any(value < 0 for value in counts):
            raise ValueError("projection counts cannot be negative")
        if self.price_provenanced_count > self.sale_eligible_count:
            raise ValueError("price-provenanced count exceeds eligible inventory")
        if any(value > self.canonical_rows_evaluated for value in counts[1:]):
            raise ValueError("projection component exceeds evaluated rows")
        if (
            self.sale_eligible_count + self.withdrawal_unknown_excluded_count
            > self.canonical_rows_evaluated
        ):
            raise ValueError("eligible and excluded inventory exceed evaluated rows")
        if self.selected_reweigh_count > self.weight_only_blocked_count:
            raise ValueError("selected reweigh count exceeds weight-only blockers")
        if not isinstance(self.withdrawal_unknown_exclusion_affirmed, bool):
            raise ValueError("withdrawal exclusion affirmation must be boolean")
        if self.weight_age_days < 0:
            raise ValueError("weight age cannot be negative")
        if self.weight_observation_time_status not in {"known", "unknown"}:
            raise ValueError("weight observation-time status is invalid")
        if self.field_list_delivery_status != "completed_exact_once":
            raise ValueError("field-list delivery must remain completed exact-once")
        if not self.field_list_receipt_id.strip():
            raise ValueError("field-list receipt identity is required")
        if not re.fullmatch(r"[0-9A-F]{64}", self.field_list_receipt_sha256):
            raise ValueError("field-list receipt SHA-256 is required")
        if not re.fullmatch(r"[0-9a-f]{64}", self.field_list_message_sha256):
            raise ValueError("field-list message SHA-256 is required")
        if self.field_list_send_attempts != 1:
            raise ValueError("field-list evidence must prove one send attempt")


@dataclass(frozen=True)
class InventoryReadyCoordinationPacket:
    status: str
    usable_inventory_status: str
    usable_inventory_count: int | None
    price_provenanced_count: int | None
    weigh_next: tuple[str, ...]
    withdrawal_unknown_excluded_count: int | None
    excluded_inventory_effect: str
    next_action: str
    automatic_follow_up_instruction: Mapping[str, Any]
    withdrawal_evidence_round: Mapping[str, Any]
    protected_decisions: tuple[str, ...]
    family_actions: Mapping[str, tuple[str, ...]]
    family_question: str
    evidence_gaps: tuple[str, ...]
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


def build_sales_weighing_packet(
    demands: Sequence[CustomerDemandEvidence],
    inventory: Sequence[SaleInventoryEvidence],
    *,
    now: datetime,
    maximum_evidence_age_hours: int = 24,
) -> SalesWeighingPacket:
    """Connect SAM demand to the smallest valuable HERDMASTER weighing set."""

    if now.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    latest_demands = _latest_by_identity(
        demands,
        identity=lambda row: row.demand_id,
    )
    latest_inventory = _latest_by_identity(
        inventory,
        identity=lambda row: row.animal_ref,
    )
    fresh_demands = [
        demand
        for demand in latest_demands
        if not demand.completed
        and _fresh_enough(demand.provenance.observed_at, now, maximum_evidence_age_hours)
    ]
    fresh_inventory = [
        animal
        for animal in latest_inventory
        if not animal.completed
        and _fresh_enough(animal.provenance.observed_at, now, maximum_evidence_age_hours)
    ]
    _require_unique_family_labels(fresh_demands, "demand")
    _require_unique_family_labels(fresh_inventory, "animal")
    gaps = []
    if not fresh_demands:
        gaps.append("fresh_sam_customer_demand")
    if not fresh_inventory:
        gaps.append("fresh_herdmaster_sale_inventory_reconciliation")

    demand_by_id = {demand.demand_id: demand for demand in fresh_demands}
    usable = []
    weigh_candidates = []
    opportunities: dict[str, dict[str, Any]] = {}
    for animal in fresh_inventory:
        compatible = tuple(
            demand_id
            for demand_id in animal.compatible_demand_ids
            if demand_id in demand_by_id
        )
        usable_measurement_fresh = (
            animal.weight_observed_at is not None
            and _fresh_enough(
                animal.weight_observed_at, now, maximum_evidence_age_hours
            )
        )
        if animal.status == "usable_now" and compatible and usable_measurement_fresh:
            compatible = tuple(
                demand_id
                for demand_id in compatible
                if _measurement_matches_demand(animal, demand_by_id[demand_id])
            )
        if animal.status == "usable_now" and compatible and usable_measurement_fresh:
            usable.append(
                MappingProxyType(
                    {
                        "animal_ref": animal.animal_ref,
                        "family_label": animal.family_label,
                        "compatible_demand_ids": compatible,
                        "weight_kg": animal.current_weight_kg,
                        "weight_observed_at": (
                            animal.weight_observed_at.isoformat()
                            if animal.weight_observed_at else ""
                        ),
                        "provenance": (
                            animal.provenance.specialist,
                            animal.provenance.result_id,
                        ),
                    }
                )
            )
        if (
            animal.status == "needs_fresh_weight"
            and animal.sale_eligible_without_weight
            and compatible
        ):
            linked = [demand_by_id[demand_id] for demand_id in compatible]
            urgency = max(_demand_urgency(demand, now) for demand in linked)
            value = sum(demand.commercial_value_score for demand in linked)
            weigh_candidates.append(
                (
                    -(value + urgency),
                    animal.animal_ref,
                    MappingProxyType(
                        {
                            "animal_ref": animal.animal_ref,
                            "family_label": animal.family_label,
                            "compatible_demand_ids": compatible,
                            "unlock_score": value + urgency,
                            "reason": (
                                "HERDMASTER says weight is the remaining inventory "
                                "evidence; fresh measurement may support these SAM demands."
                            ),
                            "provenance": (
                                animal.provenance.specialist,
                                animal.provenance.result_id,
                            ),
                        }
                    ),
                )
            )
        for demand_id in compatible:
            demand = demand_by_id[demand_id]
            opportunity = opportunities.setdefault(
                demand_id,
                {
                    "demand_id": demand_id,
                    "family_label": demand.family_label,
                    "quantity": demand.quantity,
                    "needed_by": demand.needed_by.isoformat(),
                    "commercial_value_score": demand.commercial_value_score,
                    "usable_now_count": 0,
                    "measurement_candidates": 0,
                    "provenance": (
                        demand.provenance.specialist,
                        demand.provenance.result_id,
                    ),
                },
            )
            if animal.status == "usable_now" and usable_measurement_fresh:
                opportunity["usable_now_count"] += 1
            elif (
                animal.status == "needs_fresh_weight"
                and animal.sale_eligible_without_weight
            ):
                opportunity["measurement_candidates"] += 1

    remaining = {
        demand.demand_id: demand.quantity for demand in fresh_demands
    }
    for opportunity in opportunities.values():
        opportunity["usable_now_count"] = 0
        opportunity["measurement_candidates"] = 0

    allocated_usable = []
    for row, target in _match_rows_to_demand_slots(
        usable, remaining, demand_by_id, now
    ):
        remaining[target] -= 1
        opportunities[target]["usable_now_count"] += 1
        allocated_usable.append(
            MappingProxyType({**dict(row), "allocated_demand_id": target})
        )
    usable = allocated_usable

    selected_weighing = []
    candidate_rows = [row for _, _, row in weigh_candidates]
    matched_candidates = _match_rows_to_demand_slots(
        candidate_rows, remaining, demand_by_id, now
    )
    for row, target in matched_candidates[:3]:
        selected_weighing.append(
            MappingProxyType(
                {
                    **dict(row),
                    "target_demand_id": target,
                    "unlock_score": (
                        demand_by_id[target].commercial_value_score
                        + _demand_urgency(demand_by_id[target], now)
                    ),
                }
            )
        )
        remaining[target] -= 1
        opportunities[target]["measurement_candidates"] += 1
    weigh_next = tuple(selected_weighing)
    ranked_opportunities = tuple(
        MappingProxyType(value)
        for value in sorted(
            opportunities.values(),
            key=lambda row: (
                -_demand_urgency(demand_by_id[row["demand_id"]], now),
                -row["commercial_value_score"],
                row["demand_id"],
            ),
        )
    )
    question = ""
    actionable = bool(usable or weigh_next)
    status = (
        "waiting_for_evidence"
        if gaps
        else "ready"
        if actionable
        else "no_action_supported"
    )
    dad_actions = tuple(
        f"Observe the current weight for {row['family_label']}; do not record "
        "or persist it through this brief. Supply it only through the approved "
        "HERDMASTER weight-evidence rail."
        for row in weigh_next
    )
    return SalesWeighingPacket(
        status=status,
        usable_inventory_now=tuple(usable),
        weigh_next=weigh_next,
        customer_opportunity_unlocked=ranked_opportunities,
        protected_decisions=(
            "SAM must re-verify exact eligibility, current price and offer wording.",
            "Charl retains every customer-send, reservation, order and commitment decision.",
        ),
        family_actions=MappingProxyType(
            {"charl": (), "dad": dad_actions[:3], "mom": ()}
        ),
        family_question=question,
        automatic_follow_up_instruction=MappingProxyType(
            {
                "trigger": "fresh_measurements_returned",
                "owner": "oom_sakkie_coordination",
                "instruction": (
                    "When the approved HERDMASTER rail exposes fresh measurements, "
                    "prepare a read-only HERDMASTER reconciliation. If eligibility "
                    "is verified, prepare a provenance-bound inventory handoff for "
                    "SAM's read-only offer reassessment; do not dispatch it here."
                ),
                "customer_send": False,
                "farm_write": False,
                "reservation": False,
                "stock_promise": False,
                "dispatch_performed": False,
            }
        ),
        evidence_gaps=tuple(gaps),
    )


def build_inventory_ready_coordination_packet(
    projection: HerdmasterInventoryProjection,
    *,
    now: datetime,
    required_contract_version: str,
    required_source_revision: str,
    required_source_sha256: str,
    required_field_list_receipt_sha256: str,
    expected_canonical_rows: int,
    expected_sale_eligible_count: int,
    expected_withdrawal_unknown_count: int,
    maximum_projection_age_hours: int = 24,
    maximum_weight_age_days: int = 7,
) -> InventoryReadyCoordinationPacket:
    """Validate the completed aggregate inventory handover without replaying it."""

    if now.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    gaps = []
    if projection.contract_version != required_contract_version:
        gaps.append("contract_version_mismatch")
    if projection.source_revision != required_source_revision:
        gaps.append("source_revision_mismatch")
    if projection.source_sha256 != required_source_sha256:
        gaps.append("source_handover_sha256_mismatch")
    if projection.field_list_receipt_sha256 != required_field_list_receipt_sha256:
        gaps.append("field_list_receipt_sha256_mismatch")
    if projection.canonical_rows_evaluated != expected_canonical_rows:
        gaps.append("canonical_row_count_mismatch")
    if projection.sale_eligible_count != expected_sale_eligible_count:
        gaps.append("sale_eligible_count_mismatch")
    if projection.price_provenanced_count != expected_sale_eligible_count:
        gaps.append("price_provenanced_count_mismatch")
    if (
        projection.withdrawal_unknown_excluded_count
        != expected_withdrawal_unknown_count
    ):
        gaps.append("withdrawal_unknown_count_mismatch")
    if not _fresh_enough(
        projection.observed_at, now, maximum_projection_age_hours
    ):
        gaps.append("stale_or_future_projection")
    if not _fresh_enough(
        projection.provenance.observed_at, now, maximum_projection_age_hours
    ):
        gaps.append("stale_or_future_provenance")
    actual_weight_age = (now.date() - projection.weight_date).days
    if (
        actual_weight_age != projection.weight_age_days
        or actual_weight_age < 0
        or actual_weight_age > maximum_weight_age_days
    ):
        gaps.append("weight_date_or_age_mismatch")
    if projection.sale_eligible_count != projection.price_provenanced_count:
        gaps.append("eligible_inventory_price_provenance_incomplete")
    if projection.weight_only_blocked_count != 0:
        gaps.append("weight_only_blockers_present")
    if projection.selected_reweigh_count != 0:
        gaps.append("unexpected_reweigh_selection")
    if not projection.withdrawal_unknown_exclusion_affirmed:
        gaps.append("withdrawal_unknown_exclusion_unproven")

    ready = not gaps
    next_action = (
        "SAM performs the same read-only five-journey offer reassessment "
        "against the verified inventory projection with automatic sending disabled."
        if ready
        else "Obtain a fresh, matching and complete HERDMASTER projection before SAM reassessment."
    )
    return InventoryReadyCoordinationPacket(
        status="ready_for_sam_read_only_reassessment" if ready else "waiting_for_evidence",
        usable_inventory_status="available" if ready else "unavailable",
        usable_inventory_count=projection.sale_eligible_count if ready else None,
        price_provenanced_count=(
            projection.price_provenanced_count if ready else None
        ),
        weigh_next=(),
        withdrawal_unknown_excluded_count=(
            projection.withdrawal_unknown_excluded_count
            if ready and projection.withdrawal_unknown_exclusion_affirmed
            else None
        ),
        excluded_inventory_effect=(
            "Excluded withdrawal-unknown animals do not block the separately "
            "supported eligible inventory."
            if ready and projection.withdrawal_unknown_exclusion_affirmed
            else "Withdrawal exclusion conclusion is unavailable."
        ),
        next_action=next_action,
        automatic_follow_up_instruction=MappingProxyType(
            {
                "owner": "oom_sakkie_coordination",
                "target": "sam_livestock_read_only_reassessment",
                "projection_id": projection.projection_id if ready else "",
                "instruction": next_action,
                "dispatch_performed": False,
                "customer_send": False,
                "field_list_send": False,
                "field_list_replay": False,
                "farm_write": False,
                "reservation": False,
            }
        ),
        withdrawal_evidence_round=MappingProxyType(
            {
                "status": (
                    "prepared_unsent_owner_authorization_required"
                    if ready
                    else "unavailable_untrusted_projection"
                ),
                "affected_tag_count": (
                    projection.withdrawal_unknown_excluded_count
                    if ready and projection.withdrawal_unknown_exclusion_affirmed
                    else 0
                ),
                "grouped_family_questions": 1 if ready else 0,
                "owner_message_send": False,
                "owner_message_replay": False,
                "natural_response_preview_only": True,
                "explicit_preview_confirmation_required": True,
                "governed_recording_invoked": False,
                "replay_proof_required_after_confirmation": True,
                "preserve_current_eligible_count": (
                    projection.sale_eligible_count if ready else None
                ),
                "notify_sam_only_if_inventory_changes": True,
                "sam_notification_sent": False,
            }
        ),
        protected_decisions=(
            "No stock promise, reservation, order, quote or customer send is authorized.",
            "The completed owner field-list delivery must not be recreated or replayed.",
        ),
        family_actions=MappingProxyType(
            {
                "charl": (),
                "dad": (),
                "mom": (),
            }
        ),
        family_question="",
        evidence_gaps=tuple(gaps),
    )


def render_inventory_ready_coordination_packet(
    packet: InventoryReadyCoordinationPacket,
) -> str:
    usable = (
        f"{packet.usable_inventory_count} current sale-eligible, "
        f"price-provenanced animals."
        if packet.usable_inventory_status == "available"
        else "Unavailable pending matching fresh HERDMASTER evidence."
    )
    excluded = (
        f"{packet.withdrawal_unknown_excluded_count} withdrawal-unknown animals "
        "remain excluded and do not block the supported inventory."
        if packet.withdrawal_unknown_excluded_count is not None
        else packet.excluded_inventory_effect
    )
    return "\n".join(
        (
            "OOM SAKKIE — INVENTORY-READY FAMILY BRIEF",
            f"Usable inventory now: {usable}",
            "Weigh next: none.",
            f"Customer opportunity unlocked: {packet.next_action}",
            f"Excluded evidence boundary: {excluded}",
            "Protected decisions: no customer send, stock promise, reservation, "
            "order or binding quote has been authorized.",
        )
    )


def render_sales_weighing_packet(packet: SalesWeighingPacket) -> str:
    """Render the four required evidence sections without exposing private IDs."""

    lines = ["OOM SAKKIE — DEMAND TO WEIGHING BRIEF"]
    lines.append("Usable inventory now:")
    lines.extend(
        f"- {row['family_label']}: current supported measurement for "
        f"{len(row['compatible_demand_ids'])} matched opportunity packet(s)."
        for row in packet.usable_inventory_now
    )
    if not packet.usable_inventory_now:
        lines.append("- None proven by the supplied fresh evidence.")
    lines.append("Weigh next:")
    lines.extend(
        f"- {row['family_label']}: {row['reason']}"
        for row in packet.weigh_next
    )
    if not packet.weigh_next:
        lines.append("- No measurement task is supported yet.")
    lines.append("Customer opportunity unlocked:")
    lines.extend(
        f"- {row['family_label']}: {row['usable_now_count']} usable now; "
        f"{row['measurement_candidates']} potential candidate(s) pending fresh "
        "measurement and HERDMASTER re-verification."
        for row in packet.customer_opportunity_unlocked
    )
    if not packet.customer_opportunity_unlocked:
        lines.append("- Waiting for matched SAM and HERDMASTER evidence.")
    lines.append("Protected decisions:")
    lines.extend(f"- {decision}" for decision in packet.protected_decisions)
    if packet.family_question:
        lines.append(f"One family question: {packet.family_question}")
    return "\n".join(lines)


def _fresh_enough(observed_at: datetime, now: datetime, maximum_hours: int) -> bool:
    age = (now - observed_at).total_seconds() / 3600
    return 0 <= age <= maximum_hours


def _latest_by_identity(rows, *, identity):
    selected = {}
    for row in rows:
        key = identity(row)
        prior = selected.get(key)
        candidate_order = (
            row.provenance.observed_at,
            row.provenance.result_id,
            row.completed,
        )
        prior_order = (
            prior.provenance.observed_at,
            prior.provenance.result_id,
            prior.completed,
        ) if prior is not None else None
        if prior is not None and candidate_order == prior_order and row != prior:
            raise ValueError(f"conflicting duplicate evidence identity: {key}")
        if prior is None or candidate_order > prior_order:
            selected[key] = row
    return tuple(selected[key] for key in sorted(selected))


def _require_unique_family_labels(rows, kind):
    seen = {}
    for row in rows:
        prior = seen.get(row.family_label)
        identity = row.demand_id if kind == "demand" else row.animal_ref
        if prior is not None and prior != identity:
            raise ValueError(f"duplicate family-safe {kind} label")
        seen[row.family_label] = identity


def _match_rows_to_demand_slots(rows, remaining, demand_by_id, now):
    """Maximum-cardinality deterministic matching for overlapping evidence."""

    priority = lambda demand_id: (
        -(
            demand_by_id[demand_id].commercial_value_score
            + _demand_urgency(demand_by_id[demand_id], now)
        ),
        demand_id,
    )
    slots = [
        (demand_id, index)
        for demand_id in sorted(demand_by_id, key=priority)
        for index in range(max(remaining.get(demand_id, 0), 0))
    ]
    slot_owner = {}

    def compatible_slots(row):
        allowed = set(row["compatible_demand_ids"])
        return [slot for slot in slots if slot[0] in allowed]

    ordered_rows = sorted(
        rows,
        key=lambda row: (
            len(compatible_slots(row)),
            row["animal_ref"],
        ),
    )

    def augment(row, visited):
        for slot in compatible_slots(row):
            if slot in visited:
                continue
            visited.add(slot)
            owner = slot_owner.get(slot)
            if owner is None or augment(owner, visited):
                slot_owner[slot] = row
                return True
        return False

    for row in ordered_rows:
        augment(row, set())

    pairs = [(row, slot[0]) for slot, row in slot_owner.items()]
    return sorted(
        pairs,
        key=lambda pair: (
            priority(pair[1]),
            pair[0]["animal_ref"],
        ),
    )


def _measurement_matches_demand(
    animal: SaleInventoryEvidence, demand: CustomerDemandEvidence
) -> bool:
    if animal.current_weight_kg is None:
        return False
    return (
        (demand.sex == "either" or animal.sex == demand.sex)
        and demand.minimum_weight_kg
        <= animal.current_weight_kg
        <= demand.maximum_weight_kg
    )


def _demand_urgency(demand: CustomerDemandEvidence, now: datetime) -> int:
    hours = (demand.needed_by - now).total_seconds() / 3600
    if hours <= 24:
        return 100
    if hours <= 72:
        return 60
    if hours <= 168:
        return 30
    return 0


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
    welfare_exception = 0 if item.metadata.get("welfare_exception") else 1
    customer_or_exception = 0 if item.metadata.get("customer_or_exception") else 1
    internal_housekeeping = 1 if item.metadata.get("internal_housekeeping") else 0
    return (
        welfare_exception,
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
        and item.state in {WorkState.URGENT, WorkState.DUE_TODAY, WorkState.WAITING_EVIDENCE}
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
