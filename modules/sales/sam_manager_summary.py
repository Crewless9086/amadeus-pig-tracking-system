"""Typed, read-only SAM Livestock aggregate for a manager daily brief."""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from typing import Iterable, Literal, Mapping, TypedDict


CONTRACT_VERSION = "sam_manager_summary_v1"


class CoverageException(TypedDict):
    exception_type: str
    count: int
    systemic: bool


class SamManagerSummary(TypedDict):
    contract_version: Literal["sam_manager_summary_v1"]
    specialist: Literal["sam_livestock"]
    observed_at_utc: str
    period_started_at_utc: str
    status: str
    leads_received: int
    customers_answered: int
    customers_awaiting_sam: int
    customers_awaiting_customer: int
    unresolved_protected_decisions: int
    quarantines: int
    acknowledgement_closes_suppressed: int
    coverage_exceptions: list[CoverageException]
    protected_decision_types: dict[str, int]
    lane_continuously_admitting: bool
    automatic_customer_response_proven: bool
    evidence_complete: bool
    contains_customer_content: bool
    contains_individual_messages: bool
    customer_send_authorized: bool
    customer_mutation_authorized: bool
    farm_mutation_authorized: bool


_RESPONSE_STATES = {
    "none",
    "awaiting_sam",
    "provider_confirmed_answer",
    "delivery_quarantined_do_not_retry",
}
_WORKFLOW_STATES = {
    "new_customer_inbound",
    "qualification_in_progress",
    "awaiting_customer",
    "acknowledgement_close_suppressed",
    "closed_window_reengagement_required",
    "handled",
    "non_livestock",
}
_FORBIDDEN_KEYS = {
    "content", "message_content", "customer_message", "reply",
    "suggested_reply", "customer_name", "phone", "email",
}
_COVERAGE_EXCEPTION_TYPES = {
    "closed_window",
    "provider_chronology_changed",
    "provider_chronology_unavailable",
    "whatsapp_provider_identity_conflict",
    "whatsapp_provider_identity_unavailable",
}
_PROVIDER_IDENTITY_CONFLICT_REASONS = {
    f"provider_{key}_conflict"
    for key in ("account_id", "conversation_id", "contact_id", "inbox_id")
}
_PROVIDER_IDENTITY_UNBOUND_REASONS = {
    f"provider_{key}_unbound"
    for key in ("account_id", "conversation_id", "contact_id", "inbox_id")
}


def build_sam_manager_summary(
    records: Iterable[Mapping],
    *,
    period_started_at_utc: str,
    observed_at_utc: str | None = None,
    coverage_exceptions: Iterable[Mapping] = (),
    reply_window_evaluations: Iterable[Mapping] = (),
) -> SamManagerSummary:
    """Aggregate exact inbound outcomes without customer/message authority."""
    rows = [dict(row) for row in records or ()]
    observed = observed_at_utc or datetime.now(timezone.utc).isoformat()
    if not period_started_at_utc:
        raise ValueError("manager_summary_period_start_required")
    seen = set()
    response_states = Counter()
    workflow_states = Counter()
    protected_types = Counter()
    automatic_admissions = 0
    automatic_confirmed_answers = 0
    new_leads = 0
    for row in rows:
        forbidden = _FORBIDDEN_KEYS.intersection(row)
        if forbidden:
            raise ValueError("manager_summary_customer_detail_prohibited")
        identity = (
            str(row.get("account_id") or ""),
            str(row.get("inbox_id") or ""),
            str(row.get("conversation_id") or ""),
            str(row.get("inbound_message_id") or ""),
        )
        if not all(identity) or identity in seen:
            raise ValueError("manager_summary_exact_unique_identity_required")
        seen.add(identity)
        response_state = str(row.get("response_state") or "none")
        workflow_state = str(row.get("workflow_state") or "")
        if response_state not in _RESPONSE_STATES:
            raise ValueError("manager_summary_response_state_invalid")
        if workflow_state not in _WORKFLOW_STATES:
            raise ValueError("manager_summary_workflow_state_invalid")
        if row.get("livestock_context_verified") is not True:
            raise ValueError("manager_summary_livestock_evidence_required")
        if row.get("new_lead") is True:
            new_leads += 1
        if response_state == "provider_confirmed_answer" and not (
            row.get("provider_delivery_confirmed") is True
            and str(row.get("delivery_evidence_id") or "")
        ):
            raise ValueError("manager_summary_delivery_evidence_required")
        if response_state == "delivery_quarantined_do_not_retry" and not (
            row.get("automatic_retry_prohibited") is True
            and str(row.get("quarantine_evidence_id") or "")
        ):
            raise ValueError("manager_summary_quarantine_evidence_required")
        if row.get("automatically_admitted") is True:
            automatic_admissions += 1
            if response_state == "provider_confirmed_answer":
                automatic_confirmed_answers += 1
        decision_type = str(row.get("protected_decision_type") or "")
        if decision_type:
            if not str(row.get("protected_decision_evidence_id") or ""):
                raise ValueError("manager_summary_protected_decision_evidence_required")
            protected_types[decision_type] += 1
        response_states[response_state] += 1
        workflow_states[workflow_state] += 1

    exceptions = _normalize_exceptions([
        *(coverage_exceptions or ()),
        *_reply_window_coverage_exceptions(reply_window_evaluations),
    ])
    evidence_complete = not any(item["systemic"] for item in exceptions)
    attention = bool(
        response_states["awaiting_sam"]
        or protected_types
        or response_states["delivery_quarantined_do_not_retry"]
        or exceptions
    )
    if not evidence_complete:
        status = "coverage_incomplete"
    elif attention:
        status = "attention_required"
    elif rows:
        status = "healthy"
    else:
        status = "quiet_no_new_livestock_activity"
    return {
        "contract_version": CONTRACT_VERSION,
        "specialist": "sam_livestock",
        "observed_at_utc": observed,
        "period_started_at_utc": period_started_at_utc,
        "status": status,
        "leads_received": new_leads,
        "customers_answered": response_states["provider_confirmed_answer"],
        "customers_awaiting_sam": response_states["awaiting_sam"],
        "customers_awaiting_customer": workflow_states["awaiting_customer"],
        "unresolved_protected_decisions": sum(protected_types.values()),
        "quarantines": response_states["delivery_quarantined_do_not_retry"],
        "acknowledgement_closes_suppressed": workflow_states["acknowledgement_close_suppressed"],
        "coverage_exceptions": exceptions,
        "protected_decision_types": dict(sorted(protected_types.items())),
        "lane_continuously_admitting": automatic_admissions > 0,
        "automatic_customer_response_proven": automatic_confirmed_answers > 0,
        "evidence_complete": evidence_complete,
        "contains_customer_content": False,
        "contains_individual_messages": False,
        "customer_send_authorized": False,
        "customer_mutation_authorized": False,
        "farm_mutation_authorized": False,
    }


def _normalize_exceptions(values: Iterable[Mapping]) -> list[CoverageException]:
    counts: Counter[tuple[str, bool]] = Counter()
    for value in values or ():
        item = dict(value or {})
        exception_type = str(item.get("exception_type") or "")
        if exception_type not in _COVERAGE_EXCEPTION_TYPES:
            raise ValueError("manager_summary_coverage_exception_type_required")
        count = item.get("count", 1)
        if isinstance(count, bool) or not isinstance(count, int) or count < 1:
            raise ValueError("manager_summary_coverage_exception_count_invalid")
        counts[(exception_type, item.get("systemic") is True)] += count
    return [
        {"exception_type": key[0], "count": count, "systemic": key[1]}
        for key, count in sorted(counts.items())
    ]


def _reply_window_coverage_exceptions(
    evaluations: Iterable[Mapping],
) -> list[CoverageException]:
    exceptions = []
    for raw in evaluations or ():
        row = dict(raw or {})
        reason = str(row.get("reason") or "")
        if reason == "whatsapp_provider_identity_unavailable" or reason in _PROVIDER_IDENTITY_UNBOUND_REASONS:
            exception_type = "whatsapp_provider_identity_unavailable"
        elif reason in _PROVIDER_IDENTITY_CONFLICT_REASONS:
            exception_type = "whatsapp_provider_identity_conflict"
        elif reason in {
            "provider_latest_inbound_identity_conflict",
            "provider_latest_inbound_timestamp_conflict",
            "provider_latest_inbound_timestamp_invalid",
        }:
            exception_type = "provider_chronology_changed"
        else:
            continue
        exceptions.append({
            "exception_type": exception_type,
            "count": 1,
            "systemic": False,
        })
    return exceptions
